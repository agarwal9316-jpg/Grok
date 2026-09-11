package com.grokorg.desk

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

object ServerProbe {
    suspend fun isReachable(baseUrl: String, timeoutMs: Int = 3000): Boolean =
        withContext(Dispatchers.IO) {
            try {
                val url = URL("${baseUrl.trimEnd('/')}/health")
                val conn = (url.openConnection() as HttpURLConnection).apply {
                    connectTimeout = timeoutMs
                    readTimeout = timeoutMs
                    requestMethod = "GET"
                    instanceFollowRedirects = true
                }
                val code = conn.responseCode
                code in 200..399
            } catch (_: Exception) {
                // Fallback: try root
                try {
                    val url = URL(baseUrl.trimEnd('/') + "/")
                    val conn = (url.openConnection() as HttpURLConnection).apply {
                        connectTimeout = timeoutMs
                        readTimeout = timeoutMs
                        requestMethod = "GET"
                    }
                    conn.responseCode in 200..399
                } catch (_: Exception) {
                    false
                }
            }
        }
}
