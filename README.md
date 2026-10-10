# VoxelForge

**VoxelForge** คือ voxel editor ของเรา สร้างจากแนวคิด
[Goxel](https://github.com/guillaumechereau/goxel) พร้อม **MCP bridge** ให้ AI
ต่าง ๆ (Cursor, Claude Desktop ฯลฯ) สร้างและแก้โมเดล 3D ได้โดยตรง

> Goxel ต้นฉบับเป็น GPL-3.0 — VoxelForge เป็น implementation ใหม่ที่ออกแบบ
> MCP-first ไม่ได้ fork โค้ด C ของ Goxel โดยตรง แต่รองรับไฟล์ `.vox` / `.obj`
> ที่ใช้ร่วมกันได้

## ฟีเจอร์

| ฟีเจอร์ | รายละเอียด |
| --- | --- |
| 24-bit RGB | พาเลตสีเต็ม |
| Layers | หลาย layer เหมือน Goxel |
| Export | `.vox` (MagicaVoxel), `.obj` (Wavefront) |
| Import | `.vox` จาก Goxel / MagicaVoxel |
| Web Editor | Three.js 3D — คลิกวาง/ลบ voxel |
| MCP | เชื่อม Cursor, Claude, client อื่น ๆ |

## ติดตั้ง

รันจากโฟลเดอร์โปรเจกต์ ใช้ได้เหมือนกันบน Windows, macOS และ Linux:

```bash
uv sync
cd editor && npm install && cd ..
```

`uv sync` จะติดตั้งคำสั่ง `voxel-forge-mcp` ใน environment ของโปรเจกต์

## เชื่อม MCP

วิธีที่แนะนำคือให้ client เรียก console script ผ่าน `uv run --directory`
ซึ่งใช้ได้ทุกแพลตฟอร์ม — แทน `/path/to/voxel-forge` ด้วยเส้นทางจริงของ repo

### Cursor (`~/.cursor/mcp.json`)

```json
"VoxelForge": {
  "command": "uv",
  "args": ["run", "--directory", "/path/to/voxel-forge", "voxel-forge-mcp"]
}
```

### Claude Desktop

```json
{
  "mcpServers": {
    "VoxelForge": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/voxel-forge", "voxel-forge-mcp"]
    }
  }
}
```

บน Windows จะใช้ `run-mcp.bat` เป็นทางลัดก็ได้ โดยตั้ง `command` เป็น
`C:\\path\\to\\voxel-forge\\run-mcp.bat` แทน wrapper นี้เรียก entry point ที่
ติดตั้งแล้วด้วย `uv run voxel-forge-mcp` ไม่ได้รันไฟล์ Python ใน `src/` โดยตรง

ทดสอบจาก terminal ได้ด้วยคำสั่งเดียวกับที่ client ใช้:

```bash
uv run voxel-forge-mcp
```

รีสตาร์ท client แล้วตรวจ MCP panel ว่า `VoxelForge` เป็นสีเขียว

## Desktop App (ไม่ใช้เบราว์เซอร์)

### รันโปรแกรม

```bash
uv sync --extra desktop
uv run voxel-forge
```

บน Windows จะรัน `.\run-desktop.bat` จากโฟลเดอร์โปรเจกต์ก็ได้

### Build เป็น .exe (Windows)

```powershell
.\build-desktop.bat
```

ได้ที่ `dist\VoxelForge\VoxelForge.exe` — ดับเบิลคลิกเปิดได้เลย ไม่ต้องมี
Python/เบราว์เซอร์

### ฟีเจอร์ Desktop

- เปิด/บันทึก scene (JSON)
- Import `.vox` / Export `.obj` (merged), `.vox`, Roblox Luau
- Create → Build Tree (resolution 1–8)
- 3D view native (Qt3D) — หมุนกล้องด้วยเมาส์กลาง

MCP สำหรับ AI ยังใช้แยก (`voxel-forge-mcp`) — สร้าง scene ผ่าน AI แล้วเปิดใน
Desktop จาก `~/.voxel-forge/scenes/`

---

## Web Editor (ทางเลือก)

```bash
cd editor && npm install && npm run dev
```

หรือบน Windows ใช้ `.\run-editor.bat`

เปิด `http://127.0.0.1:5173` บนเครื่องเดียวกัน โดย editor จะ sync สองทางกับ MCP
ผ่าน WebSocket ที่ `ws://127.0.0.1:8765` การสร้างหรือแก้ scene ผ่าน MCP จะส่งไป
ยัง browser และการวางหรือลบ voxel ใน editor จะอัปเดต scene ฝั่ง MCP ด้วย

ทั้ง web editor และ bridge bind อยู่ที่ loopback (`127.0.0.1`) จึงเปิดจาก
เครื่องนี้เท่านั้น ไม่เปิดให้เครื่องอื่นในเครือข่ายเข้าถึง

### 2. สร้างผ่าน AI

ตัวอย่าง prompt:

> สร้างบ้าน voxel แบบ Goxel ชื่อ my_house — ฐาน 8x8 สีเทา ตัวบ้าน 6x6x4 สีขาว
> หลังคาสามเหลี่ยมสีแดง

AI จะเรียก:

1. `voxelforge_create_scene`
2. `voxelforge_fill_box` / `voxelforge_place_many`
3. `voxelforge_preview` ตรวจรูปทรง
4. `voxelforge_export_vox` หรือ `voxelforge_export_obj`

`voxelforge_fill_box` และ `voxelforge_place_many` จำกัดไม่เกิน **100,000
voxels ต่อการเรียกหนึ่งครั้ง** หากฉากใหญ่กว่านี้ให้แบ่งเป็นหลายครั้ง

### 3. เปิดใน Goxel จริง

Export `.vox` แล้วเปิดใน Goxel หรือ MagicaVoxel:

```text
~/.voxel-forge/exports/my_house.vox
```

บน Windows เส้นทางนี้คือ `%USERPROFILE%\.voxel-forge\exports\my_house.vox`

## เครื่องมือ MCP หลัก

| Tool | หน้าที่ |
| --- | --- |
| `voxelforge_about` | ข้อมูลโปรเจกต์ |
| `voxelforge_create_scene` | สร้าง scene ใหม่ |
| `voxelforge_place_many` | วาง voxel จาก JSON |
| `voxelforge_fill_box` | เติมกล่อง 3D |
| `voxelforge_add_layer` | เพิ่ม layer |
| `voxelforge_preview` | ดู ASCII preview |
| `voxelforge_export_vox` | ส่งออก .vox |
| `voxelforge_export_obj` | ส่งออก .obj |
| `voxelforge_import_vox` | นำเข้า .vox |
| `voxelforge_launch_editor` | เปิด web editor |
| `voxelforge_save` / `voxelforge_load` | บันทึก/โหลด scene |

## โฟลเดอร์ข้อมูล

อยู่ใต้ home ของผู้ใช้ (`Path.home()`) จึงใช้ได้ทุกแพลตฟอร์ม:

- Scenes: `~/.voxel-forge/scenes/`
- Exports: `~/.voxel-forge/exports/`

## สถาปัตยกรรม

```text
┌─────────────┐   stdio/MCP   ┌──────────────┐  WebSocket   ┌─────────────┐
│ Cursor AI   │ ◄───────────► │ MCP Server   │ ◄──────────► │ Web Editor  │
│ Claude etc. │               │ (Python)     │              │ (Three.js)  │
└─────────────┘               └──────────────┘              └─────────────┘
```

## เปรียบเทียบกับ cube-world-voxel-mcp

| | VoxelForge | cube-world-voxel-mcp |
| --- | --- | --- |
| จุดประสงค์ | Editor ทั่วไปแบบ Goxel | Roblox Cube World |
| ขนาด voxel | 1×1×1 | 2×2×2 studs |
| GUI | Three.js editor | ไม่มี (headless) |
| Export | .vox, .obj | Luau → Roblox |

ทั้งสองใช้ MCP คู่กันได้ใน Cursor พร้อมกัน

## License

MIT — โค้ด VoxelForge เป็นของเรา  
Goxel ต้นฉบับ: GPL-3.0
([โครงการ Goxel](https://github.com/guillaumechereau/goxel))
