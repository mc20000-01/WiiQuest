// WBBReceiver.cs
// Drop into your Unity Quest project. Reads the mapped controller state
// published by the WBB Quest Bridge app over local loopback UDP and exposes
// it as public fields you can read from any other script, e.g.:
//
//   var wbb = FindObjectOfType<WBBReceiver>();
//   float x = wbb.StickX;
//   bool jump = wbb.ButtonA;
//
// Note: both apps run on the same headset, so this uses 127.0.0.1 — no
// network setup needed on the Unity side.

using System;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using UnityEngine;

public class WBBReceiver : MonoBehaviour
{
    public int port = 50124;

    public float StickX { get; private set; }
    public float StickY { get; private set; }
    public bool ButtonA { get; private set; }
    public bool ButtonB { get; private set; }
    public bool ButtonX { get; private set; }
    public bool ButtonY { get; private set; }

    private UdpClient _client;
    private Thread _thread;
    private volatile bool _running;

    // Simple thread-safe latest-value box; avoids touching Unity APIs off the main thread.
    private volatile string _latestJson;

    void Start()
    {
        _running = true;
        _thread = new Thread(ReceiveLoop) { IsBackground = true };
        _thread.Start();
    }

    void Update()
    {
        var json = _latestJson;
        if (string.IsNullOrEmpty(json)) return;
        try
        {
            var parsed = JsonUtility.FromJson<WBBPacket>(json);
            StickX = parsed.stickX;
            StickY = parsed.stickY;
            ButtonA = parsed.a;
            ButtonB = parsed.b;
            ButtonX = parsed.x;
            ButtonY = parsed.y;
        }
        catch (Exception e)
        {
            Debug.LogWarning("WBBReceiver: bad packet " + e.Message);
        }
    }

    void ReceiveLoop()
    {
        try
        {
            _client = new UdpClient(new IPEndPoint(IPAddress.Loopback, port));
            var remote = new IPEndPoint(IPAddress.Any, 0);
            while (_running)
            {
                var data = _client.Receive(ref remote);
                _latestJson = System.Text.Encoding.UTF8.GetString(data);
            }
        }
        catch (Exception e)
        {
            Debug.LogError("WBBReceiver: " + e.Message);
        }
    }

    void OnDestroy()
    {
        _running = false;
        _client?.Close();
    }

    [Serializable]
    private class WBBPacket
    {
        public float stickX;
        public float stickY;
        public bool a;
        public bool b;
        public bool x;
        public bool y;
    }
}
