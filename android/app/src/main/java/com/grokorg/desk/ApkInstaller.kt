package com.grokorg.desk

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.util.Log
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL

/**
 * Downloads an APK to app-private cache and launches the system package installer
 * via FileProvider (required on Android N+).
 */
object ApkInstaller {
    private const val TAG = "ApkInstaller"
    const val AUTHORITY_SUFFIX = ".fileprovider"

    fun authority(context: Context): String = "${context.packageName}$AUTHORITY_SUFFIX"

    fun canInstallPackages(context: Context): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.packageManager.canRequestPackageInstalls()
        } else {
            true
        }
    }

    /** Opens system settings so the user can allow install from this app. */
    fun openUnknownSourcesSettings(activity: Activity) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES).apply {
                data = Uri.parse("package:${activity.packageName}")
            }
            activity.startActivity(intent)
        }
    }

    /**
     * Download [url] into cache/apks/. [onProgress] receives 0–100 (or -1 if unknown length).
     */
    suspend fun downloadApk(
        context: Context,
        url: String,
        onProgress: (Int) -> Unit = {}
    ): File = withContext(Dispatchers.IO) {
        val dir = File(context.cacheDir, "apks").apply { mkdirs() }
        val outFile = File(dir, "update.apk")
        if (outFile.exists()) outFile.delete()

        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 30_000
            readTimeout = 60_000
            instanceFollowRedirects = true
            setRequestProperty("Accept", "application/octet-stream,*/*")
            setRequestProperty("User-Agent", "NEHA-Android")
        }
        try {
            val code = conn.responseCode
            if (code !in 200..299) {
                throw Exception("Download HTTP $code")
            }
            val total = conn.contentLengthLong
            conn.inputStream.use { input ->
                FileOutputStream(outFile).use { output ->
                    val buf = ByteArray(64 * 1024)
                    var readTotal = 0L
                    var lastPct = -1
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        output.write(buf, 0, n)
                        readTotal += n
                        if (total > 0) {
                            val pct = ((readTotal * 100) / total).toInt().coerceIn(0, 100)
                            if (pct != lastPct) {
                                lastPct = pct
                                onProgress(pct)
                            }
                        } else {
                            onProgress(-1)
                        }
                    }
                    output.flush()
                }
            }
            if (outFile.length() < 1024) {
                outFile.delete()
                throw Exception("Downloaded file too small (${outFile.length()} bytes)")
            }
            onProgress(100)
            outFile
        } catch (e: Exception) {
            if (outFile.exists()) outFile.delete()
            Log.w(TAG, "downloadApk failed", e)
            throw e
        } finally {
            conn.disconnect()
        }
    }

    fun installApk(context: Context, apkFile: File) {
        if (!apkFile.exists() || apkFile.length() < 1024) {
            throw IllegalArgumentException("APK file missing or empty")
        }
        val uri = FileProvider.getUriForFile(context, authority(context), apkFile)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        context.startActivity(intent)
    }
}
