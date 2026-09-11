package com.grokorg.desk

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class UpdateCheckerTest {

    @Test
    fun isNewer_basicBump() {
        assertTrue(UpdateChecker.isNewer("2.1.0", "2.0.0"))
        assertTrue(UpdateChecker.isNewer("v2.1.0", "2.0.0"))
        assertTrue(UpdateChecker.isNewer("2.1.1", "2.1.0"))
    }

    @Test
    fun isNewer_sameIsFalse() {
        assertFalse(UpdateChecker.isNewer("2.1.0", "2.1.0"))
        assertFalse(UpdateChecker.isNewer("v2.1.1", "2.1.1"))
    }

    @Test
    fun isNewer_olderIsFalse() {
        assertFalse(UpdateChecker.isNewer("2.0.0", "2.1.0"))
        assertFalse(UpdateChecker.isNewer("1.9.9", "2.0.0"))
    }

    @Test
    fun isNewer_unequalLength() {
        assertTrue(UpdateChecker.isNewer("2.1", "2.0.9"))
        assertTrue(UpdateChecker.isNewer("2.1.0", "2.0"))
        assertFalse(UpdateChecker.isNewer("2.0", "2.0.1"))
    }

    @Test
    fun isNewer_stripsPreReleaseSuffix() {
        assertTrue(UpdateChecker.isNewer("2.1.0-debug", "2.0.0"))
        assertFalse(UpdateChecker.isNewer("2.1.0-beta", "2.1.0"))
    }

    @Test
    fun isNewer_emptyOrGarbage() {
        assertFalse(UpdateChecker.isNewer("", "1.0.0"))
        assertFalse(UpdateChecker.isNewer("2.0.0", ""))
        assertFalse(UpdateChecker.isNewer("abc", "1.0.0"))
    }

    @Test
    fun pickBestApk_prefersDebugSkipsUnsigned() {
        val assets = JSONArray()
            .put(asset("GrokOrgOS-2.1.1-release-unsigned.apk", "https://ex/unsigned.apk"))
            .put(asset("GrokOrgOS-2.1.1-debug.apk", "https://ex/debug.apk"))
            .put(asset("notes.txt", "https://ex/notes.txt"))
        assertEquals("https://ex/debug.apk", UpdateChecker.pickBestApkUrl(assets))
    }

    @Test
    fun pickBestApk_skipsUnsignedOnly() {
        val assets = JSONArray()
            .put(asset("GrokOrgOS-2.1.1-release-unsigned.apk", "https://ex/unsigned.apk"))
        assertEquals(null, UpdateChecker.pickBestApkUrl(assets))
    }

    @Test
    fun pickBestApk_fallbackNonDebug() {
        val assets = JSONArray()
            .put(asset("GrokOrgOS-2.1.1.apk", "https://ex/plain.apk"))
        assertEquals("https://ex/plain.apk", UpdateChecker.pickBestApkUrl(assets))
    }

    private fun asset(name: String, url: String): JSONObject =
        JSONObject().put("name", name).put("browser_download_url", url)
}
