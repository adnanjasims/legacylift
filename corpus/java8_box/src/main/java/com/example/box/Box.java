package com.example.box;

public final class Box {
    private Box() {}

    public static Integer boxed(int value) {
        return new Integer(value);
    }

    public static int plus(int left, int right) {
        return boxed(left).intValue() + boxed(right).intValue();
    }
}
