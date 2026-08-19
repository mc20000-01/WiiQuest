package com.wbb.questbridge

/** One raw reading from the balance board bridge. */
data class BoardReading(
    val seq: Long,
    val t: Double,
    val topLeft: Float,
    val topRight: Float,
    val bottomLeft: Float,
    val bottomRight: Float,
) {
    val total: Float get() = topLeft + topRight + bottomLeft + bottomRight

    /** -1 (all weight left) .. +1 (all weight right). 0 if no weight on board. */
    val balanceX: Float get() {
        val t = total
        if (t < 2f) return 0f
        return (((topRight + bottomRight) - (topLeft + bottomLeft)) / t).coerceIn(-1f, 1f)
    }

    /** -1 (all weight back) .. +1 (all weight forward/toes). 0 if no weight on board. */
    val balanceY: Float get() {
        val t = total
        if (t < 2f) return 0f
        return (((topLeft + topRight) - (bottomLeft + bottomRight)) / t).coerceIn(-1f, 1f)
    }

    companion object {
        fun fromJson(json: org.json.JSONObject): BoardReading = BoardReading(
            seq = json.optLong("seq"),
            t = json.optDouble("t"),
            topLeft = json.optDouble("top_left").toFloat(),
            topRight = json.optDouble("top_right").toFloat(),
            bottomLeft = json.optDouble("bottom_left").toFloat(),
            bottomRight = json.optDouble("bottom_right").toFloat(),
        )
    }
}

enum class Channel(val label: String) {
    NONE("None"),
    BALANCE_X("Lean left/right"),
    BALANCE_Y("Lean forward/back"),
    TOP_LEFT("Top-left cell"),
    TOP_RIGHT("Top-right cell"),
    BOTTOM_LEFT("Bottom-left cell"),
    BOTTOM_RIGHT("Bottom-right cell"),
    TOTAL_WEIGHT("Total weight"),
}

/** Reads the value of a channel from a reading, in the channel's natural units
 *  (balance axes are -1..1, weight channels are kilograms). */
fun Channel.valueFrom(r: BoardReading): Float = when (this) {
    Channel.NONE -> 0f
    Channel.BALANCE_X -> r.balanceX
    Channel.BALANCE_Y -> r.balanceY
    Channel.TOP_LEFT -> r.topLeft
    Channel.TOP_RIGHT -> r.topRight
    Channel.BOTTOM_LEFT -> r.bottomLeft
    Channel.BOTTOM_RIGHT -> r.bottomRight
    Channel.TOTAL_WEIGHT -> r.total
}
