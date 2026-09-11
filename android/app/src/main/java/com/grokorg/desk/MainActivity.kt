package com.grokorg.desk

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.grokorg.desk.databinding.ActivityMainBinding
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: AppPrefs

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = AppPrefs(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayShowTitleEnabled(true)

        val versionName = try {
            packageManager.getPackageInfo(packageName, 0).versionName ?: "1.1.0"
        } catch (_: Exception) {
            "1.1.0"
        }
        val versionCode = try {
            @Suppress("DEPRECATION")
            packageManager.getPackageInfo(packageName, 0).versionCode
        } catch (_: Exception) {
            2
        }
        binding.versionText.text = getString(R.string.version_fmt, versionName, versionCode)

        binding.btnOpenDesk.setOnClickListener {
            startActivity(Intent(this, DeskActivity::class.java).apply {
                putExtra(DeskActivity.EXTRA_MODE, DeskActivity.MODE_SERVER)
            })
        }
        binding.btnOffline.setOnClickListener {
            startActivity(Intent(this, DeskActivity::class.java).apply {
                putExtra(DeskActivity.EXTRA_MODE, DeskActivity.MODE_OFFLINE)
            })
        }
        binding.btnSettings.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        binding.btnCheckUpdates.setOnClickListener { checkUpdates(manual = true) }

        binding.toolbar.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                R.id.action_check_updates -> {
                    checkUpdates(manual = true); true
                }
                R.id.action_settings -> {
                    startActivity(Intent(this, SettingsActivity::class.java)); true
                }
                else -> false
            }
        }
        binding.toolbar.inflateMenu(R.menu.main_menu)

        if (prefs.autoCheckUpdates) {
            checkUpdates(manual = false)
        }
    }

    override fun onResume() {
        super.onResume()
        refreshServerStatus()
    }

    private fun refreshServerStatus() {
        val url = prefs.serverUrl
        binding.serverUrlText.text = url
        binding.statusText.text = getString(R.string.status_checking)
        binding.statusText.setTextColor(getColor(R.color.warn))
        lifecycleScope.launch {
            val ok = ServerProbe.isReachable(url)
            if (ok) {
                binding.statusText.text = getString(R.string.status_online)
                binding.statusText.setTextColor(getColor(R.color.ok))
            } else {
                binding.statusText.text = getString(R.string.status_offline)
                binding.statusText.setTextColor(getColor(R.color.danger))
            }
        }
    }

    private fun checkUpdates(manual: Boolean) {
        lifecycleScope.launch {
            val result = UpdateChecker.fetchLatest()
            result.fold(
                onSuccess = { release ->
                    val current = try {
                        packageManager.getPackageInfo(packageName, 0).versionName ?: "1.1.0"
                    } catch (_: Exception) {
                        "1.1.0"
                    }
                    if (UpdateChecker.isNewer(release.tagName, current)) {
                        UpdateChecker.showUpdateDialog(this@MainActivity, release)
                    } else if (manual) {
                        Toast.makeText(
                            this@MainActivity,
                            R.string.up_to_date,
                            Toast.LENGTH_SHORT
                        ).show()
                    }
                },
                onFailure = { e ->
                    if (manual) {
                        Toast.makeText(
                            this@MainActivity,
                            "Update check failed: ${e.message}",
                            Toast.LENGTH_LONG
                        ).show()
                    }
                }
            )
        }
    }
}
