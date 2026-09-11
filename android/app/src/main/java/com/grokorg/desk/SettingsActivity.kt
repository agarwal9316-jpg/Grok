package com.grokorg.desk

import android.os.Bundle
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

        binding.serverUrlInput.setText(prefs.serverUrl)
        binding.autoUpdateSwitch.isChecked = prefs.autoCheckUpdates

        binding.btnSave.setOnClickListener {
            val url = binding.serverUrlInput.text?.toString()?.trim().orEmpty()
            if (url.isEmpty() || (!url.startsWith("http://") && !url.startsWith("https://"))) {
                Toast.makeText(this, "Enter a valid http(s) URL", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            prefs.serverUrl = url
            prefs.autoCheckUpdates = binding.autoUpdateSwitch.isChecked
            Toast.makeText(this, "Saved", Toast.LENGTH_SHORT).show()
            finish()
        }
    }
}
