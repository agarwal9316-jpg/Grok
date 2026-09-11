package com.grokorg.desk

import android.app.Application
import com.grokorg.desk.server.LocalBackend

class GrokApplication : Application() {
    lateinit var backend: LocalBackend
        private set

    override fun onCreate() {
        super.onCreate()
        backend = LocalBackend.get(this)
    }
}
