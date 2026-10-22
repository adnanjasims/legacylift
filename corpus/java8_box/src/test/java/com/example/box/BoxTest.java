package com.example.box;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BoxTest {
    @Test
    void boxedHoldsValue() {
        assertEquals(7, Box.boxed(7).intValue());
    }

    @Test
    void plusAdds() {
        assertEquals(10, Box.plus(4, 6));
    }
}
