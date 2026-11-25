import AppKit

signal(SIGPIPE, SIG_IGN)
let app = NSApplication.shared
let host = Host()
app.setActivationPolicy(.accessory)
app.delegate = host
app.run()
