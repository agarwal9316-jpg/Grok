package com.grokorg.desk

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
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

    @Test
    fun httpErrorMessage_maps403And429ToRateLimit() {
        assertEquals(UpdateChecker.RATE_LIMIT_MESSAGE, UpdateChecker.httpErrorMessage(403))
        assertEquals(UpdateChecker.RATE_LIMIT_MESSAGE, UpdateChecker.httpErrorMessage(429))
        assertTrue(UpdateChecker.httpErrorMessage(403).contains("rate limit", ignoreCase = true))
        assertEquals("GitHub API HTTP 500", UpdateChecker.httpErrorMessage(500))
        assertEquals("GitHub API HTTP 404", UpdateChecker.httpErrorMessage(404))
    }

    @Test
    fun shouldTryFallback_onRateLimitAndNetwork() {
        assertTrue(UpdateChecker.shouldTryFallback(Exception(UpdateChecker.RATE_LIMIT_MESSAGE)))
        assertTrue(UpdateChecker.shouldTryFallback(Exception("GitHub API HTTP 403")))
        assertTrue(UpdateChecker.shouldTryFallback(Exception("GitHub API HTTP 429")))
        assertTrue(UpdateChecker.shouldTryFallback(Exception("Connection reset")))
        assertTrue(UpdateChecker.shouldTryFallback(java.net.UnknownHostException("api.github.com")))
        assertFalse(UpdateChecker.shouldTryFallback(Exception("GitHub API HTTP 404")))
        assertFalse(UpdateChecker.shouldTryFallback(Exception("GitHub API HTTP 500")))
        assertFalse(UpdateChecker.shouldTryFallback(null))
    }

    @Test
    fun parseFallbackReleaseJson_readsDebugApkUrl() {
        val json = """
            {
              "tag":"v2.1.4",
              "versionName":"2.1.4",
              "versionCode":9,
              "apkUrl":"https://github.com/agarwal9316-jpg/Grok/releases/download/v2.1.4/NEHA-2.1.4-debug.apk",
              "htmlUrl":"https://github.com/agarwal9316-jpg/Grok/releases/tag/v2.1.4"
            }
        """.trimIndent()
        val info = UpdateChecker.parseFallbackReleaseJson(json)
        assertEquals("v2.1.4", info.tagName)
        assertEquals("2.1.4", info.name)
        assertEquals(
            "https://github.com/agarwal9316-jpg/Grok/releases/download/v2.1.4/NEHA-2.1.4-debug.apk",
            info.apkUrl
        )
        assertEquals(
            "https://github.com/agarwal9316-jpg/Grok/releases/tag/v2.1.4",
            info.htmlUrl
        )
        assertTrue(UpdateChecker.isNewer(info.tagName, "2.1.2"))
    }

    @Test
    fun parseApiReleaseJson_picksDebugAsset() {
        val json = JSONObject()
            .put("tag_name", "v2.1.4")
            .put("name", "N.E.H.A v2.1.4")
            .put("body", "notes")
            .put("html_url", "https://github.com/agarwal9316-jpg/Grok/releases/tag/v2.1.4")
            .put(
                "assets",
                JSONArray()
                    .put(asset("NEHA-2.1.4-release-unsigned.apk", "https://ex/unsigned.apk"))
                    .put(asset("NEHA-2.1.4-debug.apk", "https://ex/debug.apk"))
            )
            .toString()
        val info = UpdateChecker.parseApiReleaseJson(json)
        assertEquals("v2.1.4", info.tagName)
        assertEquals("https://ex/debug.apk", info.apkUrl)
        assertNotNull(info.apkUrl)
    }

    private fun asset(name: String, url: String): JSONObject =
        JSONObject().put("name", name).put("browser_download_url", url)
}
