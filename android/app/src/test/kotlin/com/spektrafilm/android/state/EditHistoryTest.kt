package com.spektrafilm.android.state

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class EditHistoryTest {
    @Test
    fun undoRedoReturnsParamStatesInOrder() {
        val base = SpektrafilmParams()
        val first = base.withExposureCompensation(0.25f)
        val second = first.withPrintExposure(1.15f)
        val history = EditHistory(base)

        history.push(first)
        history.push(second)

        assertTrue(history.canUndo)
        assertFalse(history.canRedo)
        assertEquals(first, history.undo())
        assertEquals(base, history.undo())
        assertFalse(history.canUndo)
        assertEquals(first, history.redo())
        assertEquals(second, history.redo())
        assertFalse(history.canRedo)
    }

    @Test
    fun pushingNewStateClearsRedoAndHonorsMaxSize() {
        val base = SpektrafilmParams()
        val history = EditHistory(base, maxSize = 2)
        val first = base.withExposureCompensation(0.25f)
        val second = base.withExposureCompensation(0.5f)
        val third = base.withExposureCompensation(0.75f)

        history.push(first)
        history.push(second)
        assertEquals(first, history.undo())
        history.push(third)

        assertFalse(history.canRedo)
        assertEquals(first, history.undo())
        assertFalse(history.canUndo)
    }
}
