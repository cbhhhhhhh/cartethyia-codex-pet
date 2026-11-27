#import <Foundation/Foundation.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
/* Best effort only. Never return a decision to Codex. No prompts or tool
 * arguments on IPC. */
int main(void) {
  @autoreleasepool {
    // The Stop family expects JSON. An empty object makes no decision.
    puts("{}");
    if (getenv("PET_PLUS_INTERNAL")) return 0;
    NSString *base =
        [NSHomeDirectory() stringByAppendingPathComponent:
                               @"Library/Application Support/CodexPetPlus"];
    NSString *override = NSProcessInfo.processInfo.environment[@"PET_PLUS_HOME"];
    if ([override isAbsolutePath])
      base = override;
    NSString *token = [NSString
        stringWithContentsOfFile:[base stringByAppendingPathComponent:@"token"]
                        encoding:NSUTF8StringEncoding
                           error:nil];
    if (!token)
      return 0;
    NSMutableData *data = [NSMutableData data];
    char chunk[8192];
    ssize_t n;
    while ((n = read(STDIN_FILENO, chunk, sizeof chunk)) > 0) {
      if (data.length + n > 1048576)
        return 0;
      [data appendBytes:chunk length:n];
    }
    NSDictionary *j = [NSJSONSerialization JSONObjectWithData:data
                                                      options:0
                                                        error:nil];
    if (![j isKindOfClass:NSDictionary.class])
      return 0;
    NSDictionary *map = @{
      @"UserPromptSubmit" : @"start",
      @"PreToolUse" : @"tool",
      @"PostToolUse" : @"result",
      @"PermissionRequest" : @"approval",
      @"Interrupt" : @"abort",
      @"Stop" : @"stop-attempt",
      @"SubagentStop" : @"stop-attempt"
    };
    NSString *event = j[@"hook_event_name"];
    if (![event isKindOfClass:NSString.class] || !map[event] || [event isEqual:@"SubagentStop"])
      return 0;
    NSMutableDictionary *m = [@{
      @"v" : @1,
      @"kind" : map[event],
      @"token" : token,
      @"source" : @"hook"
    } mutableCopy];
    NSDictionary *fields = @{
      @"thread" : [event isEqual:@"SubagentStop"] ? @"agent_id" : @"session_id",
      @"turn" : @"turn_id",
      @"tool" : @"tool_name",
      @"call" : @"tool_use_id"
    };
    for (NSString *key in fields) {
      id v = j[fields[key]];
      if ([v isKindOfClass:NSString.class] && [v length] <= 160)
        m[key] = v;
    }
    NSData *body = [NSJSONSerialization dataWithJSONObject:m
                                                   options:0
                                                     error:nil];
    struct sockaddr_un addr = {.sun_family = AF_UNIX};
    NSString *path = [base stringByAppendingPathComponent:@"events.sock"];
    if (strlen(path.fileSystemRepresentation) >= sizeof addr.sun_path)
      return 0;
    strlcpy(addr.sun_path, path.fileSystemRepresentation, sizeof addr.sun_path);
    int fd = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (fd >= 0) {
      fcntl(fd, F_SETFL, O_NONBLOCK);
      sendto(fd, body.bytes, body.length, MSG_DONTWAIT,
             (struct sockaddr *)&addr, sizeof addr);
      close(fd);
    }
    return 0;
  }
}
