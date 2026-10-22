package com.example.urlkit;

import java.net.MalformedURLException;
import java.net.URL;

public final class UrlKit {
    private UrlKit() {}

    public static URL parse(String spec) throws MalformedURLException {
        return new URL(spec);
    }

    public static String host(String spec) throws MalformedURLException {
        return parse(spec).getHost();
    }
}
