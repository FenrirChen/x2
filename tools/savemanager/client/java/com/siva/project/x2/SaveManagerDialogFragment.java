package com.siva.project.x2;

import android.app.AlertDialog;
import android.app.Dialog;
import android.app.DialogFragment;
import android.content.DialogInterface;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.Charset;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * Save manager dialog: export/import the server-side archive of the currently
 * authenticated account. Pure programmatic Android UI (no resources), storage
 * access via the Storage Access Framework only, and the save token is
 * single-purpose and short-lived. Nothing here is persisted to disk by the app
 * itself; export/import files are chosen by the user through SAF.
 */
public class SaveManagerDialogFragment extends DialogFragment {

    private static final int REQUEST_EXPORT = 42101;
    private static final int REQUEST_IMPORT_PICK = 42102;
    private static final int MAX_SAVE_BYTES = 96 * 1024 * 1024;

    private String account;
    private String password;
    private String baseUrl;
    private String saveToken;

    private Button exportButton;
    private Button importButton;
    private TextView statusText;

    private byte[] pendingExportBytes;
    private byte[] pendingImportBytes;
    private boolean busy;

    @Override
    public Dialog onCreateDialog(Bundle savedInstanceState) {
        Bundle args = getArguments();
        account = args != null ? args.getString("account", "") : "";
        password = args != null ? args.getString("password", "") : "";
        baseUrl = args != null ? args.getString("baseUrl", "") : "";
        while (baseUrl.endsWith("/")) baseUrl = baseUrl.substring(0, baseUrl.length() - 1);

        LinearLayout root = new LinearLayout(getActivity());
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(20);
        root.setPadding(pad, dp(8), pad, dp(12));

        TextView accountView = new TextView(getActivity());
        accountView.setText("当前账号：" + account);
        accountView.setTextSize(16);
        accountView.setTextColor(Color.parseColor("#333333"));
        root.addView(accountView);

        statusText = new TextView(getActivity());
        statusText.setTextColor(Color.parseColor("#666666"));
        statusText.setTextSize(13);
        statusText.setPadding(0, dp(6), 0, 0);
        root.addView(statusText);

        exportButton = styledButton("导出存档", 0xFF4A7EBB);
        exportButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                startExport();
            }
        });
        root.addView(exportButton, matchWrap());

        importButton = styledButton("导入存档", 0xFFB85C38);
        importButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                startImportPick();
            }
        });
        root.addView(importButton, matchWrap());

        Button closeButton = styledButton("返回", 0xFF666666);
        closeButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                getDialog().dismiss();
            }
        });
        root.addView(closeButton, matchWrap());

        AlertDialog dialog = new AlertDialog.Builder(getActivity())
                .setTitle("存档管理")
                .setView(root)
                .create();
        return dialog;
    }

    // -- export ---------------------------------------------------------------

    private void startExport() {
        if (busy) return;
        setBusy(true, "正在导出存档…");
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    ensureToken();
                    HttpResult result = httpPost(baseUrl + "/save-manager/export", null,
                            "application/octet-stream", saveToken, 120000);
                    byte[] payload = result.body;
                    if (result.status != 200 || payload == null || payload.length < 4
                            || payload[0] != 'P' || payload[1] != 'K') {
                        fail("服务器返回了无效的存档数据");
                        return;
                    }
                    pendingExportBytes = payload;
                    ui(new Runnable() {
                        @Override
                        public void run() {
                            setBusy(false, "存档已获取，请选择保存位置");
                            String stamp = new SimpleDateFormat(
                                    "yyyyMMdd_HHmmss", Locale.US).format(new Date());
                            Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                            intent.addCategory(Intent.CATEGORY_OPENABLE);
                            intent.setType("application/octet-stream");
                            intent.putExtra(Intent.EXTRA_TITLE,
                                    "X2_" + account + "_" + stamp + ".x2save");
                            startActivityForResult(intent, REQUEST_EXPORT);
                        }
                    });
                } catch (AuthException e) {
                    fail("账号或密码错误");
                } catch (Exception e) {
                    fail("导出失败：" + shortMessage(e));
                }
            }
        }).start();
    }

    // -- import ---------------------------------------------------------------

    private void startImportPick() {
        if (busy) return;
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/octet-stream");
        startActivityForResult(intent, REQUEST_IMPORT_PICK);
    }

    private void confirmImport(final byte[] payload) {
        new AlertDialog.Builder(getActivity())
                .setTitle("确认导入")
                .setMessage("导入存档将覆盖当前账号的全部游戏进度。\n服务器会在导入前自动创建备份。\n是否继续？")
                .setNegativeButton("取消", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface dialog, int which) {
                        setBusy(false, "已取消导入");
                    }
                })
                .setPositiveButton("继续导入", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface dialog, int which) {
                        runImport(payload);
                    }
                })
                .show();
    }

    private void runImport(final byte[] payload) {
        setBusy(true, "正在导入存档…");
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    ensureToken();
                    HttpResult result = httpPost(baseUrl + "/save-manager/import", payload,
                            "application/octet-stream", saveToken, 120000);
                    JSONObject response = new JSONObject(new String(
                            result.body, Charset.forName("UTF-8")));
                    if (result.status == 401) {
                        fail("登录状态已过期，请重试");
                        return;
                    }
                    if (result.status != 200 || !"ok".equals(response.optString("code"))) {
                        String message = response.optString("message", "");
                        String error = response.optString("error", "");
                        if ("account_online".equals(error)) {
                            fail(TextUtils.isEmpty(message)
                                    ? "账号当前在线，请先退出游戏后再导入存档。" : message);
                        } else if ("invalid_save".equals(error)) {
                            fail(TextUtils.isEmpty(message) ? "存档文件无效" : "导入失败：" + message);
                        } else {
                            fail(TextUtils.isEmpty(message) ? "导入失败：" + error : message);
                        }
                        return;
                    }
                    ui(new Runnable() {
                        @Override
                        public void run() {
                            busy = false;
                            new AlertDialog.Builder(getActivity())
                                    .setTitle("存档管理")
                                    .setMessage("存档导入成功，请重新登录。")
                                    .setCancelable(false)
                                    .setPositiveButton("确定", new DialogInterface.OnClickListener() {
                                        @Override
                                        public void onClick(DialogInterface dialog, int which) {
                                            dismiss();
                                        }
                                    })
                                    .show();
                        }
                    });
                } catch (AuthException e) {
                    fail("账号或密码错误");
                } catch (Exception e) {
                    fail("导入失败：" + shortMessage(e));
                }
            }
        }).start();
    }

    // -- auth ---------------------------------------------------------------

    private void ensureToken() throws Exception {
        if (saveToken != null) return;
        // auth endpoint expects an urlencoded form; build it manually
        StringBuilder body = new StringBuilder();
        body.append("account=").append(urlEncode(account));
        body.append("&password=").append(urlEncode(password));
        HttpResult result = httpPost(baseUrl + "/save-manager/auth",
                body.toString().getBytes(Charset.forName("UTF-8")),
                "application/x-www-form-urlencoded", null, 15000);
        if (result.status == 404) {
            throw new Exception("服务器尚未启用存档管理接口，请更新服务端");
        }
        if (result.status != 200) throw new Exception("存档认证服务异常（HTTP " + result.status + "）");
        JSONObject json = new JSONObject(new String(result.body, Charset.forName("UTF-8")));
        String code = json.optString("code");
        if ("ok".equals(code)) {
            saveToken = json.optString("token");
            if (TextUtils.isEmpty(saveToken)) throw new Exception("empty token");
        } else if ("invalid".equals(code) || "empty".equals(code)) {
            throw new AuthException();
        } else {
            throw new Exception("auth failed: " + code);
        }
    }

    private static String urlEncode(String value) {
        try {
            return java.net.URLEncoder.encode(value, "UTF-8");
        } catch (Exception e) {
            return "";
        }
    }

    // -- HTTP -----------------------------------------------------------------

    private static class AuthException extends Exception {
    }

    private static class HttpResult {
        final int status;
        final byte[] body;

        HttpResult(int status, byte[] body) {
            this.status = status;
            this.body = body;
        }
    }

    private HttpResult httpPost(String url, byte[] body, String contentType,
                                String token, int timeoutMs) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        try {
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(15000);
            connection.setReadTimeout(timeoutMs);
            connection.setDoOutput(true);
            connection.setUseCaches(false);
            if (token != null) {
                connection.setRequestProperty("Authorization", "Bearer " + token);
            }
            if (body != null) {
                connection.setFixedLengthStreamingMode(body.length);
                connection.setRequestProperty("Content-Type", contentType);
                OutputStream out = connection.getOutputStream();
                out.write(body);
                out.flush();
                out.close();
            } else {
                connection.setRequestProperty("Content-Type", contentType);
            }
            int status = connection.getResponseCode();
            // Route/status only: never log request bodies, credentials or tokens.
            android.util.Log.i("X2SaveManager", "HTTP " + new URL(url).getPath() + " status=" + status);
            InputStream stream = status >= 400
                    ? connection.getErrorStream() : connection.getInputStream();
            return new HttpResult(status, readAll(stream));
        } finally {
            connection.disconnect();
        }
    }

    private static byte[] readAll(InputStream stream) throws Exception {
        if (stream == null) return new byte[0];
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        byte[] chunk = new byte[16384];
        int read;
        while ((read = stream.read(chunk)) != -1) {
            buffer.write(chunk, 0, read);
        }
        stream.close();
        return buffer.toByteArray();
    }

    // -- SAF results ------------------------------------------------------------

    @Override
    public void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (resultCode != android.app.Activity.RESULT_OK || data == null
                || data.getData() == null) {
            setBusy(false, "已取消");
            return;
        }
        final Uri uri = data.getData();
        if (requestCode == REQUEST_EXPORT) {
            final byte[] payload = pendingExportBytes;
            pendingExportBytes = null;
            if (payload == null) {
                setBusy(false, "导出数据丢失，请重试");
                return;
            }
            setBusy(true, "正在保存…");
            new Thread(new Runnable() {
                @Override
                public void run() {
                    try {
                        OutputStream out = getActivity().getContentResolver()
                                .openOutputStream(uri);
                        out.write(payload);
                        out.flush();
                        out.close();
                        ui(new Runnable() {
                            @Override
                            public void run() {
                                setBusy(false, "存档导出成功");
                            }
                        });
                    } catch (final Exception e) {
                        ui(new Runnable() {
                            @Override
                            public void run() {
                                fail("保存失败：" + shortMessage(e));
                            }
                        });
                    }
                }
            }).start();
        } else if (requestCode == REQUEST_IMPORT_PICK) {
            try {
                InputStream in = getActivity().getContentResolver().openInputStream(uri);
                byte[] payload = readAll(in);
                if (payload.length > MAX_SAVE_BYTES) {
                    setBusy(false, "存档文件过大");
                    return;
                }
                if (payload.length < 4 || payload[0] != 'P' || payload[1] != 'K') {
                    setBusy(false, "不是有效的 .x2save 存档文件");
                    return;
                }
                pendingImportBytes = payload;
                setBusy(false, "");
                confirmImport(payload);
            } catch (Exception e) {
                setBusy(false, "读取文件失败：" + shortMessage(e));
            }
        }
    }

    // -- UI helpers -------------------------------------------------------------

    private void ui(Runnable runnable) {
        if (getActivity() == null) return;
        getActivity().runOnUiThread(runnable);
    }

    private void setBusy(final boolean value, final String message) {
        busy = value;
        ui(new Runnable() {
            @Override
            public void run() {
                if (exportButton != null) exportButton.setEnabled(!value);
                if (importButton != null) importButton.setEnabled(!value);
                if (statusText != null && message != null) statusText.setText(message);
            }
        });
    }

    private void fail(final String message) {
        saveToken = null;
        ui(new Runnable() {
            @Override
            public void run() {
                setBusy(false, message);
                Toast.makeText(getActivity(), message, Toast.LENGTH_LONG).show();
            }
        });
    }

    private String shortMessage(Exception e) {
        String message = e.getMessage();
        return message == null ? e.getClass().getSimpleName() : message;
    }

    private Button styledButton(String label, int color) {
        Button button = new Button(getActivity());
        button.setText(label);
        button.setTextColor(Color.WHITE);
        button.setTextSize(16);
        button.setAllCaps(false);
        GradientDrawable background = new GradientDrawable();
        background.setColor(color);
        background.setCornerRadius(dp(6));
        button.setBackgroundDrawable(background);
        button.setTypeface(Typeface.DEFAULT_BOLD);
        button.setPadding(0, dp(10), 0, dp(10));
        return button;
    }

    private LinearLayout.LayoutParams matchWrap() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.topMargin = dp(10);
        params.gravity = Gravity.CENTER_HORIZONTAL;
        return params;
    }

    private int dp(int value) {
        float scale = getResources().getDisplayMetrics().density;
        return (int) (value * scale + 0.5f);
    }
}
