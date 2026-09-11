# Grok Org OS — keep WebView / update classes
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
