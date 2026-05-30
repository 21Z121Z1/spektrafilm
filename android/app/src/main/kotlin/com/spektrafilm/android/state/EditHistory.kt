package com.spektrafilm.android.state

class EditHistory<T>(
    initial: T,
    private val maxSize: Int = 50,
) {
    init {
        require(maxSize >= 2) { "maxSize must keep at least current and one undo state" }
    }

    private val undoStack = ArrayDeque<T>()
    private val redoStack = ArrayDeque<T>()

    var current: T = initial
        private set

    val canUndo: Boolean
        get() = undoStack.isNotEmpty()

    val canRedo: Boolean
        get() = redoStack.isNotEmpty()

    fun push(next: T): T {
        if (next == current) {
            return current
        }
        undoStack.addLast(current)
        while (undoStack.size > maxSize - 1) {
            undoStack.removeFirst()
        }
        redoStack.clear()
        current = next
        return current
    }

    fun undo(): T {
        if (undoStack.isEmpty()) {
            return current
        }
        redoStack.addLast(current)
        current = undoStack.removeLast()
        return current
    }

    fun redo(): T {
        if (redoStack.isEmpty()) {
            return current
        }
        undoStack.addLast(current)
        while (undoStack.size > maxSize - 1) {
            undoStack.removeFirst()
        }
        current = redoStack.removeLast()
        return current
    }
}
