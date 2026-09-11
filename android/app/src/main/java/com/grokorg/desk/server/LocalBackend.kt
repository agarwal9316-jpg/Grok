package com.grokorg.desk.server

import android.content.Context
import android.util.Log
import java.net.ServerSocket

/**
 * Starts/stops the on-device NanoHTTPD backend bound to 127.0.0.1.
 */
class LocalBackend(context: Context) {
    private val appContext = context.applicationContext
    val store = OrgStore(appContext)
    @Volatile var port: Int = DEFAULT_PORT
        private set
    @Volatile var isRunning: Boolean = false
        private set

    private var server: LocalHttpServer? = null

    @Synchronized
    fun start() {
        if (isRunning && server != null) return
        store.ensureBootstrapped()
        port = findFreePort(DEFAULT_PORT)
        val srv = LocalHttpServer(appContext, store, HOST, port)
        srv.start(NanoTimeout, false)
        server = srv
        isRunning = true
        Log.i(TAG, "Local backend listening on http://$HOST:$port/")
    }

    @Synchronized
    fun stop() {
        try {
            server?.stop()
        } catch (_: Exception) {
        }
        server = null
        isRunning = false
    }

    fun ensureStarted(): Int {
        if (!isRunning) start()
        return port
    }

    fun baseUrl(): String = "http://$HOST:${ensureStarted()}"

    private fun findFreePort(preferred: Int): Int {
        // Try preferred first
        try {
            ServerSocket(preferred).use { return preferred }
        } catch (_: Exception) {
        }
        ServerSocket(0).use { return it.localPort }
    }

    companion object {
        const val HOST = "127.0.0.1"
        const val DEFAULT_PORT = 8765
        private const val NanoTimeout = 10_000
        private const val TAG = "LocalBackend"

        @Volatile
        private var instance: LocalBackend? = null

        fun get(context: Context): LocalBackend {
            return instance ?: synchronized(this) {
                instance ?: LocalBackend(context).also {
                    instance = it
                    it.start()
                }
            }
        }
    }
}
