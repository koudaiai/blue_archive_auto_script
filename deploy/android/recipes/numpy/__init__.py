from pythonforandroid.recipe import Recipe, MesonRecipe
from pythonforandroid.recipe import PyProjectRecipe as _PyProjectRecipe
from pythonforandroid.logger import error
from os.path import join, dirname
import glob
import shutil

# 全局修复 p4a 的 PEP517 构建隔离问题。
# PyProjectRecipe.build_arch() 用 `python -m build --wheel`，默认创建隔离环境；
# 而 PythonRecipe.get_recipe_env() 把 PYTHONPATH 指向交叉编译 hostpython3 的
# 源码 Lib/ —— 那里只有纯 .py，没有 math / _posixsubprocess / select 等 C 扩展。
# 隔离环境继承该 PYTHONPATH 后，numpy 报缺 _posixsubprocess、Pillow 报缺 math，
# 本质是同一个病根。这里在 recipe 加载阶段给基类补参数，让所有继承
# PyProjectRecipe 且未自行覆盖 extra_build_args 的 recipe（Pillow、lxml 等）
# 都在已经能正常运行的 hostpython3 里构建；它们各自声明的
# hostpython_prerequisites（如 Pillow 的 setuptools>=77）由
# PyProjectRecipe.build_arch 负责安装，不依赖隔离环境。
# 注意 numpy 自己覆盖了 extra_build_args，所以下面 NumpyRecipe 里也保留了这两个参数。
for _flag in ('--no-isolation', '--skip-dependency-check'):
    if _flag not in _PyProjectRecipe.extra_build_args:
        _PyProjectRecipe.extra_build_args.append(_flag)

NUMPY_NDK_MESSAGE = "In order to build numpy, you must set minimum ndk api (minapi) to `24`.\n"


class NumpyRecipe(MesonRecipe):
    version = 'v1.26.5'
    url = 'git+https://github.com/numpy/numpy'
    # p4a 的 PyProjectRecipe 用 `python -m build --wheel`，默认开启 PEP517 构建隔离；
    # 而 PythonRecipe.get_recipe_env 把 PYTHONPATH 指向交叉编译 hostpython3 的源码 Lib/，
    # 那里只有 .py 没有 C 扩展。隔离环境里 mesonpy 一 import subprocess 就报
    # "ModuleNotFoundError: No module named '_posixsubprocess'"。
    # 关掉隔离，直接让后端跑在已能正常工作的 hostpython3 里。版本按 numpy v1.26.5
    # 的 pyproject.toml [build-system].requires 精确固定。
    hostpython_prerequisites = [
        "Cython>=3.0.6,<3.1",
        "meson-python>=0.15.0,<0.16.0",
    ]
    extra_build_args = [
        '-Csetup-args=-Dblas=none',
        '-Csetup-args=-Dlapack=none',
        '--no-isolation',
        '--skip-dependency-check',
    ]
    need_stl_shared = True

    def get_recipe_meson_options(self, arch):
        options = super().get_recipe_meson_options(arch)
        # Custom python is required, so that meson
        # gets libs and config files properly
        options["binaries"]["python"] = self.ctx.python_recipe.python_exe
        options["binaries"]["python3"] = self.ctx.python_recipe.python_exe
        options["properties"]["longdouble_format"] = "IEEE_DOUBLE_LE" if arch.arch in ["armeabi-v7a", "x86"] else "IEEE_QUAD_LE"
        return options

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)

        # _PYTHON_HOST_PLATFORM declares that we're cross-compiling
        # and avoids issues when building on macOS for Android targets.
        env["_PYTHON_HOST_PLATFORM"] = arch.command_prefix

        # NPY_DISABLE_SVML=1 allows numpy to build for non-AVX512 CPUs
        # See: https://github.com/numpy/numpy/issues/21196
        env["NPY_DISABLE_SVML"] = "1"
        env["TARGET_PYTHON_EXE"] = join(Recipe.get_recipe(
                "python3", self.ctx).get_build_dir(arch.arch), "android-build", "python")

        # 兜底：万一 build 仍创建了隔离环境，把 hostpython3 实际编译出的 C 扩展
        # 目录（_posixsubprocess / _struct / select ...）补进 PYTHONPATH。
        # p4a 只加了源码 Lib/ 和顶层 build/，扩展常编在 native-build 下而漏掉。
        try:
            host_root = dirname(dirname(self.real_hostpython_location))
            so_dirs = {
                dirname(so) for so in glob.glob(
                    join(host_root, '**', '_posixsubprocess*.so'), recursive=True)
            }
            pythonpath = env.get('PYTHONPATH', '')
            for lib_dir in so_dirs:
                if lib_dir not in pythonpath.split(':'):
                    pythonpath = lib_dir + ':' + pythonpath
            env['PYTHONPATH'] = pythonpath
        except Exception:
            pass
        return env

    def download_if_necessary(self):
        # NumPy requires complex math functions which were added in api 24
        if self.ctx.ndk_api < 24:
            error(NUMPY_NDK_MESSAGE)
            exit(1)
        super().download_if_necessary()

    def build_arch(self, arch):
        super().build_arch(arch)
        self.restore_hostpython_prerequisites(["cython"])

    def get_hostrecipe_env(self, arch):
        env = super().get_hostrecipe_env(arch)
        env['RANLIB'] = shutil.which('ranlib')
        env.setdefault("LDFLAGS", "")
        env["LDFLAGS"] += " -lm"
        return env


recipe = NumpyRecipe()