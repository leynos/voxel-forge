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

```powershell
cd C:\Users\thana\Desktop\voxel-forge
uv sync
cd editor
npm install
```

`uv sync` จะติดตั้งคำสั่ง `voxel-forge-mcp` ใน environment ของโปรเจกต์

## เชื่อม MCP

### Cursor (`~/.cursor/mcp.json`)

```json
"VoxelForge": {
  "command": "C:\\Users\\thana\\Desktop\\voxel-forge\\run-mcp.bat",
  "args": []
}
```

### Claude Desktop

```json
{
  "mcpServers": {
    "VoxelForge": {
      "command": "C:\\Users\\thana\\Desktop\\voxel-forge\\run-mcp.bat",
      "args": []
    }
  }
}
```

`run-mcp.bat` เป็น wrapper สำหรับ Windows ที่เรียก entry point ที่ติดตั้งแล้ว
ด้วย `uv run voxel-forge-mcp` ไม่ได้รันไฟล์ Python ใน `src/` โดยตรง หากต้องการ
ทดสอบจาก PowerShell ให้รันคำสั่งนี้จากโฟลเดอร์โปรเจกต์:

```powershell
uv run voxel-forge-mcp
```

รีสตาร์ท client แล้วตรวจ MCP panel ว่า `VoxelForge` เป็นสีเขียว

## Desktop App (ไม่ใช้เบราว์เซอร์)

### รันโปรแกรม

```powershell
cd C:\Users\thana\Desktop\voxel-forge
.\run-desktop.bat
```

หรือหลัง `uv sync --extra desktop`:

```powershell
uv run voxel-forge
```

### Build เป็น .exe

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

MCP สำหรับ AI ยังใช้แยก (`run-mcp.bat`) — สร้าง scene ผ่าน AI แล้วเปิดใน
Desktop จาก `%USERPROFILE%\.voxel-forge\scenes\`

---

## Web Editor (ทางเลือก)

```powershell
.\run-editor.bat
```

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
%USERPROFILE%\.voxel-forge\exports\my_house.vox
```

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

- Scenes: `%USERPROFILE%\.voxel-forge\scenes\`
- Exports: `%USERPROFILE%\.voxel-forge\exports\`

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
