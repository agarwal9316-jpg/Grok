package com.grokorg.desk

import android.annotation.SuppressLint
import android.graphics.Bitmap
import android.os.Bundle
import android.view.View
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.grokorg.desk.databinding.ActivityDeskBinding
import com.grokorg.desk.server.LocalBackend
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class DeskActivity : AppCompatActivity() {
    private lateinit var binding: ActivityDeskBinding
    private lateinit var prefs: AppPrefs
    private var fellBackToOffline = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityDeskBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = AppPrefs(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        binding.toolbar.setNavigationOnClickListener { finish() }

        val mode = intent.getStringExtra(EXTRA_MODE) ?: MODE_SERVER

        val web = binding.webView
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            cacheMode = WebSettings.LOAD_DEFAULT
            useWideViewPort = true
            loadWithOverviewMode = true
            builtInZoomControls = true
            displayZoomControls = false
            allowFileAccess = true
            allowContentAccess = true
        }
        web.webChromeClient = WebChromeClient()
        web.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                binding.progress.visibility = View.VISIBLE
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                binding.progress.visibility = View.GONE
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                if (request?.isForMainFrame == true && mode == MODE_SERVER && !fellBackToOffline) {
                    fellBackToOffline = true
                    Toast.makeText(
                        this@DeskActivity,
                        R.string.status_offline,
                        Toast.LENGTH_LONG
                    ).show()
                    loadOfflineShell()
                }
            }
        }

        if (mode == MODE_OFFLINE) {
            binding.toolbar.title = getString(R.string.demo_offline)
            loadOfflineShell()
        } else {
            binding.toolbar.title = getString(R.string.desk_title)
            lifecycleScope.launch {
                val base = withContext(Dispatchers.IO) {
                    if (prefs.useOnDevice) {
                        LocalBackend.get(this@DeskActivity).baseUrl()
                    } else {
                        prefs.remoteServerUrl
                    }
                }
                val ok = ServerProbe.isReachable(base)
                if (ok) {
                    web.loadUrl("$base/")
                } else {
                    Toast.makeText(
                        this@DeskActivity,
                        R.string.status_offline,
                        Toast.LENGTH_LONG
                    ).show()
                    loadOfflineShell()
                }
            }
        }
    }

    private fun loadOfflineShell() {
        binding.toolbar.title = getString(R.string.demo_offline)
        binding.webView.loadUrl("file:///android_asset/www/offline.html")
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (binding.webView.canGoBack()) {
            binding.webView.goBack()
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }

    companion object {
        const val EXTRA_MODE = "mode"
        const val MODE_SERVER = "server"
        const val MODE_OFFLINE = "offline"
    }
}
