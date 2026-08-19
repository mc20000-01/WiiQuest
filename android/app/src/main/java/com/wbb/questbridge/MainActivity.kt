package com.wbb.questbridge

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.ArrayAdapter
import androidx.appcompat.app.AppCompatActivity
import com.wbb.questbridge.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var receiver: UdpBoardReceiver
    private lateinit var config: MappingConfig
    private lateinit var publisher: OutputPublisher

    private var lastReading: BoardReading? = null
    private val uiHandler = Handler(Looper.getMainLooper())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        config = MappingConfig(this).apply { load() }
        receiver = UdpBoardReceiver(port = 50123)
        publisher = OutputPublisher(config.outputPort)

        binding.listenPortValue.text = "50123"
        binding.outputPortInput.setText(config.outputPort.toString())

        setupChannelSpinner(binding.stickXSpinner, config.stickXSource) { config.stickXSource = it }
        setupChannelSpinner(binding.stickYSpinner, config.stickYSource) { config.stickYSource = it }
        setupChannelSpinner(binding.buttonASpinner, config.buttonA.source) { config.buttonA.source = it }
        setupChannelSpinner(binding.buttonBSpinner, config.buttonB.source) { config.buttonB.source = it }
        setupChannelSpinner(binding.buttonXSpinner, config.buttonX.source) { config.buttonX.source = it }
        setupChannelSpinner(binding.buttonYSpinner, config.buttonY.source) { config.buttonY.source = it }

        binding.saveButton.setOnClickListener {
            config.outputPort = binding.outputPortInput.text.toString().toIntOrNull() ?: config.outputPort
            config.save()
            publisher.close()
            publisher = OutputPublisher(config.outputPort)
            binding.statusText.text = "Mapping saved."
        }

        receiver.latestReading.observe(this) { reading ->
            lastReading = reading
            renderReading(reading)
        }

        receiver.start()
        startPublishLoop()
    }

    private fun setupChannelSpinner(
        spinner: android.widget.Spinner,
        initial: Channel,
        onSelected: (Channel) -> Unit,
    ) {
        val labels = Channel.values().map { it.label }
        spinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, labels)
        spinner.setSelection(Channel.values().indexOf(initial))
        spinner.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(
                parent: android.widget.AdapterView<*>?, view: android.view.View?, pos: Int, id: Long,
            ) = onSelected(Channel.values()[pos])
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
        }
    }

    private fun renderReading(r: BoardReading) {
        binding.rawValues.text =
            "TL %.1f  TR %.1f\nBL %.1f  BR %.1f\nTotal %.1f kg".format(
                r.topLeft, r.topRight, r.bottomLeft, r.bottomRight, r.total
            )
        binding.balanceValues.text =
            "Lean X %.2f   Lean Y %.2f".format(r.balanceX, r.balanceY)
    }

    /** At ~60Hz: apply the current mapping to the latest reading and publish
     *  it over loopback UDP for consumption by your own Quest app. */
    private fun startPublishLoop() {
        val intervalMs = 16L
        val tick = object : Runnable {
            override fun run() {
                val r = lastReading
                val connected = (System.currentTimeMillis() - (receiver.lastPacketMillis.value ?: 0L)) < 1000
                binding.connectionStatus.text = if (connected) "Bridge: connected" else "Bridge: waiting..."

                if (r != null) {
                    val sx = config.stickValue(config.stickXSource, r)
                    val sy = config.stickValue(config.stickYSource, r)
                    val a = config.buttonPressed(config.buttonA, r)
                    val b = config.buttonPressed(config.buttonB, r)
                    val x = config.buttonPressed(config.buttonX, r)
                    val y = config.buttonPressed(config.buttonY, r)
                    publisher.publish(sx, sy, a, b, x, y)
                }
                uiHandler.postDelayed(this, intervalMs)
            }
        }
        uiHandler.post(tick)
    }

    override fun onDestroy() {
        super.onDestroy()
        receiver.stop()
        publisher.close()
    }
}
