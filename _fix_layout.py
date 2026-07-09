path = r"C:\Users\zq\PycharmProjects\AI_NOTE\frontend\src\pages\AppShell\GlobalQA.tsx"
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find the message rendering block and wrap it
for i, line in enumerate(lines):
    # Find the line '              <div key={i} className={`flex gap-2 ${'
    if 'key={i}' in line and 'flex gap-2' in line and i > 100:
        start = i
        # Wrap the opening <div> - change to <div><div className=...>
        lines[i] = lines[i].replace(
            '<div key={i} className={`flex gap-2 ${',
            '<div>\n                <div key={i} className={`flex gap-2 ${'
        )
        
        # Find the closing </div> (the flex container close)
        depth = 0
        for j in range(i, len(lines)):
            if '</div>' in lines[j]:
                if depth == 0:
                    end = j
                    # This is the flex container closing </div>
                    # Change it to: </div>\n{Array.isArray(msg.sources) && <div className="pl-9"><SourceReferences sources={msg.sources} /></div>}\n              </div>
                    d = chr(34)
                    indent = "                "
                    lines[j] = lines[j].replace(
                        '</div>',
                        '</div>\n'
                        + indent + '{Array.isArray(msg.sources) && <div className=' + d + 'pl-9' + d + '><SourceReferences sources={msg.sources} /></div>}\n'
                        + '              </div>'
                    )
                    break
            # Track div depth for nested divs
            if '<div' in lines[j] and '</div>' not in lines[j]:
                depth += 1
            elif '</div>' in lines[j] and '<div' not in lines[j]:
                if depth > 0:
                    depth -= 1
                else:
                    break
        break

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Fixed: SourceReferences below message content")