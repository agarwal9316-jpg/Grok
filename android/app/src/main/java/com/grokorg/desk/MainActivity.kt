package com.grokorg.desk

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.grokorg.desk.databinding.ActivityMainBinding
import com.grokorg.desk.server.LocalBackend
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: AppPrefs

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = AppPrefs(this)

        // Ensure local backend is up
        LocalBackend.get(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayShowTitleEnabled(true)

        val versionName = try {
            packageManager.getPackageInfo(packageName, 0).versionName ?: "1.2.0"
        } catch (_: Exception) {
            "1.2.0"
        }
        val versionCode = try {
            @Suppress("DEPRECATION")
            packageManager.getPackageInfo(packageName, 0).versionCode
        } catch (_: Exception) {
            3
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
        val url = prefs.effectiveServerUrl()
        binding.serverUrlText.text = if (prefs.useOnDevice) {
            getString(R.string.mode_on_device_label, url)
        } else {
            getString(R.string.mode_remote_label, url)
        }
        binding.statusText.text = getString(R.string.status_checking)
        binding.statusText.setTextColor(getColor(R.color.warn))
        lifecycleScope.launch {
            val ok = ServerProbe.isReachable(url)
            if (ok) {
                binding.statusText.text = if (prefs.useOnDevice) {
                    getString(R.string.status_on_device)
                } else {
                    getString(R.string.status_online)
                }
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
                        packageManager.getPackageInfo(packageName, 0).versionName ?: "1.2.0"
                    } catch (_: Exception) {
                        "1.2.0"
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
                        UpdateChecker.showCheckFailedDialog(
                            this@MainActivity,
                            e.message ?: getString(R.string.update_check_failed_generic)
                        )
                    }
                }
            )
        }
    }
}
