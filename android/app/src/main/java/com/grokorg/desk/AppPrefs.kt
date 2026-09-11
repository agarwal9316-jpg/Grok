package com.grokorg.desk

import android.content.Context
import android.content.SharedPreferences
import com.grokorg.desk.server.LocalBackend

class AppPrefs(context: Context) {
    private val appContext = context.applicationContext
    private val prefs: SharedPreferences =
        appContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    /** true = on-device standalone (default); false = advanced remote override */
    var useOnDevice: Boolean
        get() = prefs.getBoolean(KEY_USE_ON_DEVICE, true)
        set(value) = prefs.edit().putBoolean(KEY_USE_ON_DEVICE, value).apply()

    var remoteServerUrl: String
        get() = prefs.getString(KEY_REMOTE_URL, DEFAULT_REMOTE_URL)?.trim()?.trimEnd('/')
            ?: DEFAULT_REMOTE_URL
        set(value) = prefs.edit().putString(KEY_REMOTE_URL, value.trim().trimEnd('/')).apply()

    var autoCheckUpdates: Boolean
        get() = prefs.getBoolean(KEY_AUTO_UPDATE, true)
        set(value) = prefs.edit().putBoolean(KEY_AUTO_UPDATE, value).apply()

    /** Effective URL the WebView / probes should use. */
    fun effectiveServerUrl(): String {
        return if (useOnDevice) {
            LocalBackend.get(appContext).baseUrl()
        } else {
            remoteServerUrl
        }
    }

    /** @deprecated use effectiveServerUrl / useOnDevice */
    var serverUrl: String
        get() = effectiveServerUrl()
        set(value) {
            remoteServerUrl = value
            useOnDevice = false
        }

    companion object {
        const val PREFS_NAME = "grok_org_os"
        const val KEY_USE_ON_DEVICE = "use_on_device"
        const val KEY_REMOTE_URL = "remote_server_url"
        const val KEY_SERVER_URL = "server_url" // legacy
        const val KEY_AUTO_UPDATE = "auto_check_updates"
        const val DEFAULT_REMOTE_URL = "http://10.0.2.2:8000"
    }
}
