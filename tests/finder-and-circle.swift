import AppKit
import ApplicationServices

// Exercise Launch Services and the WindowServer mouse route without touching a user's profile.
let path = URL(fileURLWithPath: CommandLine.arguments[1])
let support = CommandLine.arguments[2]
let reportURL = URL(fileURLWithPath: CommandLine.arguments[3])
var results: [String: Any] = [:]
func require(_ condition: Bool, _ label: String) {
  if !condition { FileHandle.standardError.write(Data(("Failed: "+label+"\n").utf8)); exit(1) }
  results[label] = true
}
func pump(_ sec: Double) { RunLoop.current.run(until: Date().addingTimeInterval(sec)) }
func wait(_ seconds: Double = 5, _ check: () -> Bool) -> Bool {
  let until=Date().addingTimeInterval(seconds)
  repeat { if check() {return true}; pump(0.018) } while Date()<until
  return check()
}
func launch(_ fresh: Bool) -> NSRunningApplication? {
  let conf=NSWorkspace.OpenConfiguration()
  conf.createsNewApplicationInstance=fresh
  conf.environment=["PET_PLUS_HOME":support,"CODEX_HOME":support+"/empty"]
  var app:NSRunningApplication?
  var finished=false
  NSWorkspace.shared.openApplication(at:path,configuration:conf) { result,_ in app=result; finished=true }
  _ = wait(8) { finished }
  return app
}
let prefs = URL(fileURLWithPath:support).appendingPathComponent("profiles/main/config.json")
let before = try JSONSerialization.jsonObject(with:Data(contentsOf:prefs)) as! NSDictionary
guard let instance=launch(true) else { exit(2) }
let pid=instance.processIdentifier
func frame(_ title: String) -> CGRect? {
  let info=CGWindowListCopyWindowInfo([.optionOnScreenOnly,.excludeDesktopElements],kCGNullWindowID) as? [[String:Any]] ?? []
  guard let w=info.first(where: { ($0[kCGWindowOwnerPID as String] as? Int32)==pid && ($0[kCGWindowName as String] as? String)==title }),
    let bounds=w[kCGWindowBounds as String] as? NSDictionary else{return nil}
  return CGRect(dictionaryRepresentation:bounds)
}
func mouse(_ kind: CGEventType, _ at: CGPoint) {
  let event=CGEvent(mouseEventSource:nil, mouseType:kind,mouseCursorPosition:at,mouseButton:.left)!
  event.setIntegerValueField(.mouseEventClickState,value:1)
  event.post(tap:.cghidEventTap)
}
func run() {
  let title="卡提 · 设置"
  require(wait { frame(title) != nil }, "finder_cold_open_shows_settings")
  // The accessory does not install a standard application menu, so close the test's red window control.
  let after = (try? Data(contentsOf:prefs)).flatMap { try? JSONSerialization.jsonObject(with:$0) } as? NSDictionary
  require(after?.isEqual(to:before as! [AnyHashable:Any]) == true, "existing_profile_settings_values_preserved")
  let position=CGEvent(source:nil)!.location
  defer { mouse(.mouseMoved,position) }
  var w = frame(title)!
  let red=CGPoint(x:w.minX+14,y:w.minY+14)
  require(CGPreflightPostEventAccess(),"quartz_event_posting_available")
  mouse(.mouseMoved,red);pump(0.10);mouse(.leftMouseDown,red);pump(0.05);mouse(.leftMouseUp,red)
  require(wait {frame(title)==nil},"settings_closed_before_reopen")
  require(launch(false)?.processIdentifier==pid,"finder_reopen_uses_existing_process")
  require(wait {frame(title) != nil},"finder_reopen_reveals_settings")
  w=frame(title)!
  let again=CGPoint(x:w.minX+14,y:w.minY+14)
  mouse(.mouseMoved,again);pump(0.10);mouse(.leftMouseDown,again);pump(0.05);mouse(.leftMouseUp,again)
  require(wait {frame(title)==nil},"settings_closed_before_quartz_gesture")
  let name="Cartethyia Companion"
  guard let pet=frame(name) else {return require(false,"desktop_character_visible")}
  let start=CGPoint(x:pet.midX,y:pet.midY)
  mouse(.mouseMoved,start);pump(0.42)
  require(wait { frame("卡提 · 工作详情") != nil }, "windowserver_mouse_hits_character")
  mouse(.leftMouseDown,start);pump(0.045)
  for i in 1...24 {
    let angle=2*Double.pi*Double(i)/24
    mouse(.leftMouseDragged,CGPoint(x:start.x + 33*(cos(angle)-1),y:start.y + 33*sin(angle)))
    pump(0.014)
  }
  mouse(.leftMouseUp,start)
  var sign=0.0, lastX=start.x, edge=false, bounced=false, maxTravel=0.0
  let bounds=CGDisplayBounds(CGMainDisplayID())
  let stop=Date().addingTimeInterval(3)
  while Date()<stop && !bounced {
    pump(0.013)
    guard let f=frame(name) else {continue}
    let delta=f.midX-lastX
    if sign==0 && abs(delta)>6 {sign=delta>0 ? 1 : -1}
    maxTravel=max(maxTravel,abs(f.midX-start.x))
    if min(abs(f.minX-bounds.minX),abs(bounds.maxX-f.maxX)) < 64 {edge=true}
    if edge && sign*delta < -2 {bounced=true}
    lastX=f.midX
  }
  results["quartz_closed_circle_max_horizontal_points"]=Int(maxTravel.rounded())
  require(maxTravel>120 && bounced,"quartz_closed_circle_hits_wall_and_reverses")
}
run()
_ = instance.terminate()
let bytes=try JSONSerialization.data(withJSONObject:results,options:[.prettyPrinted,.sortedKeys])
try bytes.write(to:reportURL)
