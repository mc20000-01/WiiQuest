package com.wbb.questbridge

import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

/**
 * Publishes the mapped virtual-controller state to 127.0.0.1:[port] as a
 * JSON line, at whatever rate [publish] is called. Any app you build on the
 * headset (Unity, Godot, a raw socket) can read this trivially — see
 * unity/WBBReceiver.cs for a minimal example.
 *
 * Packet shape:
 *   {"stickX": 0.42, "stickY": -0.10,
 *    "a": false, "b": false, "x": true, "y": false}
 */
class OutputPublisher(private val port: Int) {
    private val socket = DatagramSocket()
    private val loopback = InetAddress.getByName("127.0.0.1")

    fun publish(stickX: Float, stickY: Float, a: Boolean, b: Boolean, x: Boolean, y: Boolean) {
        val json = JSONObject()
            .put("stickX", stickX)
            .put("stickY", stickY)
            .put("a", a)
            .put("b", b)
            .put("x", x)
            .put("y", y)
        val bytes = json.toString().toByteArray(Charsets.UTF_8)
        val packet = DatagramPacket(bytes, bytes.size, loopback, port)
        try {
            socket.send(packet)
        } catch (_: Exception) {
            // best-effort; dropped frames are fine for a live control stream
        }
    }

    fun close() = socket.close()
}
