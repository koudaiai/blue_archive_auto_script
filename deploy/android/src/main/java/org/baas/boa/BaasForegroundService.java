package org.baas.boa;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

/**
 * 常驻前台服务：把 Python 所在的进程提升到前台优先级。
 *
 * 目的只有一个——屏幕熄灭、Activity 进入后台之后，系统不会把这套 Python
 * 当成 cached 进程冻结（Android 12+ 的 Cached Apps Freezer 会 SIGSTOP 掉
 * 后台进程，导致调度定时器停摆）。
 *
 * 不申请任何特权：只用系统自带的前台服务机制 + 一条不可清除的低优先级通知，
 * 不改动任何系统设置。
 */
public class BaasForegroundService extends Service {
    private static final String TAG = "BaasForeground";
    private static final String CHANNEL_ID = "baas_runtime";
    private static final String CHANNEL_NAME = "BAAS 运行状态";
    private static final int NOTIFICATION_ID = 1001;

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel(this);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        try {
            startForeground(NOTIFICATION_ID, buildNotification(this));
        } catch (Exception error) {
            Log.w(TAG, "startForeground failed: " + error);
        }
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    /** 供 Python 侧调用：幂等地拉起前台服务。 */
    public static void ensureRunning(Context context) {
        if (context == null) {
            return;
        }
        try {
            Intent intent = new Intent(context, BaasForegroundService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent);
            } else {
                context.startService(intent);
            }
        } catch (Exception error) {
            Log.w(TAG, "ensureRunning failed: " + error);
        }
    }

    private static void createChannel(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (manager == null) {
            return;
        }
        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID, CHANNEL_NAME, NotificationManager.IMPORTANCE_LOW);
        channel.setShowBadge(false);
        channel.setSound(null, null);
        manager.createNotificationChannel(channel);
    }

    private static Notification buildNotification(Context context) {
        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(context, CHANNEL_ID);
        } else {
            builder = new Notification.Builder(context);
        }
        return builder
                .setContentTitle("BAAS 运行中")
                .setContentText("熄屏后仍会继续执行定时任务")
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setOngoing(true)
                .build();
    }
}
