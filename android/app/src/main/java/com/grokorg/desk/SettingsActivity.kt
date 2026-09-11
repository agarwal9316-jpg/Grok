package com.grokorg.desk

import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.grokorg.desk.databinding.ActivitySettingsBinding

class SettingsActivity : AppCompatActivity() {
    private lateinit var binding: ActivitySettingsBinding
    private lateinit var prefs: AppPrefs

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = AppPrefs(this)

        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        binding.toolbar.setNavigationOnClickListener { finish() }

        binding.modeOnDevice.isChecked = prefs.useOnDevice
        binding.modeRemote.isChecked = !prefs.useOnDevice
        binding.serverUrlInput.setText(prefs.remoteServerUrl)
        binding.autoUpdateSwitch.isChecked = prefs.autoCheckUpdates
        updateRemoteVisibility()

        binding.modeGroup.setOnCheckedChangeListener { _, checkedId ->
            updateRemoteVisibility()
        }

        binding.btnSave.setOnClickListener {
            val onDevice = binding.modeOnDevice.isChecked
            prefs.useOnDevice = onDevice
            prefs.autoCheckUpdates = binding.autoUpdateSwitch.isChecked
            if (!onDevice) {
                val url = binding.serverUrlInput.text?.toString()?.trim().orEmpty()
                if (url.isEmpty() || (!url.startsWith("http://") && !url.startsWith("https://"))) {
                    Toast.makeText(this, "Enter a valid http(s) URL", Toast.LENGTH_SHORT).show()
                    return@setOnClickListener
                }
                prefs.remoteServerUrl = url
            }
            Toast.makeText(this, "Saved", Toast.LENGTH_SHORT).show()
            finish()
        }
    }

    private fun updateRemoteVisibility() {
        val remote = binding.modeRemote.isChecked
        binding.remoteSection.visibility = if (remote) View.VISIBLE else View.GONE
    }
}
