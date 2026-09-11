package com.grokorg.desk

import android.content.Context
import android.content.SharedPreferences

class AppPrefs(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    var serverUrl: String
        get() = prefs.getString(KEY_SERVER_URL, DEFAULT_SERVER_URL)?.trim()?.trimEnd('/')
            ?: DEFAULT_SERVER_URL
        set(value) = prefs.edit().putString(KEY_SERVER_URL, value.trim().trimEnd('/')).apply()

    var autoCheckUpdates: Boolean
        get() = prefs.getBoolean(KEY_AUTO_UPDATE, true)
        set(value) = prefs.edit().putBoolean(KEY_AUTO_UPDATE, value).apply()

    companion object {
        const val PREFS_NAME = "grok_org_os"
        const val KEY_SERVER_URL = "server_url"
        const val KEY_AUTO_UPDATE = "auto_check_updates"
        /** Emulator loopback to host machine running Start.bat / FastAPI. */
        const val DEFAULT_SERVER_URL = "http://10.0.2.2:8000"
    }
}
