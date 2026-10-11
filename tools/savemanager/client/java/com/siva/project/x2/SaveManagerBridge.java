package com.siva.project.x2;

import android.app.Activity;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;

/**
 * Java entry point called from the native save-manager bridge through
 * UnityEngine.AndroidJavaClass. Runs on a Unity engine thread; everything the
 * user sees must be marshalled to the UI thread. Credentials live only in
 * memory (intent/argument extras) and are never persisted or logged.
 */
public class SaveManagerBridge {

    public static void open(final String account, final String password, final String baseUrl) {
        final Activity activity = com.unity3d.player.UnityPlayer.currentActivity;
        if (activity == null) {
            return;
        }
        final Handler handler = new Handler(Looper.getMainLooper());
        handler.post(new Runnable() {
            @Override
            public void run() {
                if (account == null || account.length() == 0
                        || password == null || password.length() == 0) {
                    Toast.makeText(activity, "请输入账号和密码", Toast.LENGTH_SHORT).show();
                    return;
                }
                if (baseUrl == null || baseUrl.length() == 0) {
                    Toast.makeText(activity, "无法获取服务器地址", Toast.LENGTH_SHORT).show();
                    return;
                }
                SaveManagerDialogFragment fragment = new SaveManagerDialogFragment();
                android.os.Bundle args = new android.os.Bundle();
                args.putString("account", account);
                args.putString("password", password);
                args.putString("baseUrl", baseUrl);
                fragment.setArguments(args);
                fragment.show(activity.getFragmentManager(), "x2-save-manager");
            }
        });
    }
}
