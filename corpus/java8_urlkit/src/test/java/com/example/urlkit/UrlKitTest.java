package com.example.urlkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class UrlKitTest {
    @Test
    void hostFromHttp() throws Exception {
        assertEquals("example.com", UrlKit.host("http://example.com/path"));
    }

    @Test
    void parseProtocol() throws Exception {
        assertEquals("https", UrlKit.parse("https://example.com").getProtocol());
    }
}
