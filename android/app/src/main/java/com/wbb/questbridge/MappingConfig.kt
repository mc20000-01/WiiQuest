package com.wbb.questbridge

import android.content.Context

/** A button fires when its source channel crosses [thresholdKg] (weight
 *  channels) or [thresholdKg]/10 as a -1..1 threshold (balance channels). */
data class ButtonMapping(
    var source: Channel = Channel.NONE,
    var thresholdKg: Float = 10f,
)

/** Holds the full mapping from board channels to virtual controller outputs,
 *  and persists it to SharedPreferences so it survives app restarts. */
class MappingConfig(context: Context) {
    private val prefs = context.getSharedPreferences("wbb_mapping", Context.MODE_PRIVATE)

    var stickXSource: Channel = Channel.BALANCE_X
    var stickYSource: Channel = Channel.BALANCE_Y
    var stickDeadzone: Float = 0.08f

    val buttonA = ButtonMapping(Channel.NONE, 15f)
    val buttonB = ButtonMapping(Channel.NONE, 15f)
    val buttonX = ButtonMapping(Channel.NONE, 15f)
    val buttonY = ButtonMapping(Channel.NONE, 15f)

    var outputPort: Int = 50124

    fun load() {
        stickXSource = Channel.valueOf(prefs.getString("stickX", Channel.BALANCE_X.name)!!)
        stickYSource = Channel.valueOf(prefs.getString("stickY", Channel.BALANCE_Y.name)!!)
        stickDeadzone = prefs.getFloat("deadzone", 0.08f)
        loadButton("A", buttonA)
        loadButton("B", buttonB)
        loadButton("X", buttonX)
        loadButton("Y", buttonY)
        outputPort = prefs.getInt("outPort", 50124)
    }

    private fun loadButton(key: String, b: ButtonMapping) {
        b.source = Channel.valueOf(prefs.getString("btn${key}Src", Channel.NONE.name)!!)
        b.thresholdKg = prefs.getFloat("btn${key}Thr", 15f)
    }

    fun save() {
        prefs.edit().apply {
            putString("stickX", stickXSource.name)
            putString("stickY", stickYSource.name)
            putFloat("deadzone", stickDeadzone)
            saveButton("A", buttonA, this)
            saveButton("B", buttonB, this)
            saveButton("X", buttonX, this)
            saveButton("Y", buttonY, this)
            putInt("outPort", outputPort)
        }.apply()
    }

    private fun saveButton(key: String, b: ButtonMapping, editor: android.content.SharedPreferences.Editor) {
        editor.putString("btn${key}Src", b.source.name)
        editor.putFloat("btn${key}Thr", b.thresholdKg)
    }

    /** Applies deadzone + clamping appropriate for the given source channel. */
    fun stickValue(source: Channel, reading: BoardReading): Float {
        var v = source.valueFrom(reading)
        // Weight-cell channels aren't naturally -1..1; only balance axes are
        // sensible stick sources, but we still guard so nothing NaNs out.
        if (source == Channel.BALANCE_X || source == Channel.BALANCE_Y) {
            if (kotlin.math.abs(v) < stickDeadzone) v = 0f
        } else {
            v = 0f
        }
        return v.coerceIn(-1f, 1f)
    }

    fun buttonPressed(b: ButtonMapping, reading: BoardReading): Boolean {
        if (b.source == Channel.NONE) return false
        val v = b.source.valueFrom(reading)
        return if (b.source == Channel.BALANCE_X || b.source == Channel.BALANCE_Y) {
            kotlin.math.abs(v) * 100f >= b.thresholdKg // reuse slider as % for balance channels
        } else {
            v >= b.thresholdKg
        }
    }
}
