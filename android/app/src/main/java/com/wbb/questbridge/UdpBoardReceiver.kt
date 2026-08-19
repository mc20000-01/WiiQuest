package com.wbb.questbridge

import android.util.Log
import androidx.lifecycle.MutableLiveData
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.SocketTimeoutException

/**
 * Listens for JSON board packets from wbb_bridge.py on [port] and republishes
 * them as LiveData. Also tracks last-packet time so the UI can show whether
 * the bridge is currently connected.
 */
class UdpBoardReceiver(private val port: Int) {

    val latestReading = MutableLiveData<BoardReading>()
    val lastPacketMillis = MutableLiveData<Long>(0L)

    @Volatile private var running = false
    private var socket: DatagramSocket? = null
    private var thread: Thread? = null

    fun start() {
        if (running) return
        running = true
        thread = Thread {
            try {
                val sock = DatagramSocket(port)
                sock.soTimeout = 1000
                socket = sock
                val buf = ByteArray(512)
                while (running) {
                    try {
                        val packet = DatagramPacket(buf, buf.size)
                        sock.receive(packet)
                        val text = String(packet.data, 0, packet.length, Charsets.UTF_8)
                        val json = JSONObject(text)
                        val reading = BoardReading.fromJson(json)
                        latestReading.postValue(reading)
                        lastPacketMillis.postValue(System.currentTimeMillis())
                    } catch (_: SocketTimeoutException) {
                        // normal — lets us check `running` periodically
                    } catch (e: Exception) {
                        Log.w("UdpBoardReceiver", "Bad packet: ${e.message}")
                    }
                }
                sock.close()
            } catch (e: Exception) {
                Log.e("UdpBoardReceiver", "Receiver failed to bind port $port", e)
            }
        }.also { it.isDaemon = true; it.start() }
    }

    fun stop() {
        running = false
        socket?.close()
        thread = null
    }
}
