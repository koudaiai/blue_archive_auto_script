from enum import Enum, auto

# 更新追踪的分支：koudaiai fork 上的自改分支
REPO_BRANCH = "fix/cafe-invite-fuzzy-name"

class GetShaMethod(Enum):
    GITHUB_API = auto()
    PYGIT2 = auto()
    MIRRORC_API = auto()


get_remote_sha_methods = [
    {
        "name": "github",
        "method": GetShaMethod.GITHUB_API,
        "owner": "koudaiai",
        "repo": "blue_archive_auto_script",
        "branch": REPO_BRANCH,
    },
    {
        "name": "mirrorc",
        "method": GetShaMethod.MIRRORC_API,
    },
    {
        "name": "gitee",
        "method": GetShaMethod.PYGIT2,
        "url": "https://gitee.com/pur1fy/blue_archive_auto_script.git",
        "branch": REPO_BRANCH,
    },
    {
        "name": "gitcode",
        "method": GetShaMethod.PYGIT2,
        "url": "https://gitcode.com/m0_74686738/blue_archive_auto_script.git",
        "branch": REPO_BRANCH,
    },
    {
        "name": "tencent_c_coding",
        "method": GetShaMethod.PYGIT2,
        "url": "https://e.coding.net/g-jbio0266/baas/blue_archive_auto_script.git",
        "branch": REPO_BRANCH,
    }
]
