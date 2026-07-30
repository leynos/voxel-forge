# VoxelForge

**VoxelForge** คือ voxel editor ที่มาพร้อม **MCP bridge** ให้ AI assistant
ต่าง ๆ (Cursor, Claude Desktop ฯลฯ) สร้างและแก้โมเดล 3D ได้โดยตรง

English: [README.md](README.md)

> **ที่มาของโค้ด** repository นี้ (`leynos/voxel-forge`) เป็น soft fork ของ
> [thanakon228/voxel-forge](https://github.com/thanakon228/voxel-forge) —
> VoxelForge ต้นฉบับโดย thanakon228 ตัว VoxelForge เองได้แนวคิดมาจาก
> [Goxel](https://github.com/guillaumechereau/goxel) (GPL-3.0) แต่เป็น
> implementation อิสระที่ออกแบบแบบ MCP-first ไม่ได้ fork โค้ด C ของ Goxel
> และสองโครงการใช้ร่วมกันเพียงรูปแบบไฟล์ `.vox` กับ `.obj` ที่แลกเปลี่ยน
> กันได้เท่านั้น รายละเอียดดู [docs/provenance.md](docs/provenance.md) และ
> [docs/fork-and-interface-boundary.md](docs/fork-and-interface-boundary.md)

## ฟีเจอร์

| ฟีเจอร์ | รายละเอียด |
| --- | --- |
| 24-bit RGB | พาเลตสีเต็ม |
| Layers | หลาย layer เหมือน Goxel |
| Export | `.vox` (MagicaVoxel), `.obj` (Wavefront) |
| Import | `.vox` จาก Goxel / MagicaVoxel |
| Web editor | Three.js 3D — คลิกวาง/ลบ voxel |
| MCP | เชื่อม Cursor, Claude, client อื่น ๆ |

## การติดตั้ง

VoxelForge ติดตั้งเป็น Python tool มาตรฐานได้ทั้งบน Linux, macOS และ
Windows วิธีที่แนะนำคือใช้ [uv](https://docs.astral.sh/uv/):

```bash
uv tool install git+https://github.com/leynos/voxel-forge
```

คำสั่งนี้จะวาง console script สามตัวไว้ใน `PATH` ของคุณ:

| คำสั่ง | หน้าที่ |
| --- | --- |
| `voxel-forge-mcp` | MCP server ผ่าน stdio (อินเทอร์เฟซหลัก) |
| `voxel-forge-bridge` | WebSocket/HTTP bridge แบบแยกสำหรับ web editor |
| `voxel-forge` | Desktop app แบบ native (ต้องมี extra `desktop`) |

สำหรับ desktop app ให้ติดตั้งพร้อม extra:

```bash
uv tool install 'voxel-forge[desktop] @ git+https://github.com/leynos/voxel-forge'
```

หากทำงานจาก checkout แทน:

```bash
git clone https://github.com/leynos/voxel-forge
cd voxel-forge
uv sync            # add --extra desktop for the desktop app
uv run voxel-forge-mcp
```

## การเชื่อมต่อ MCP client

ตั้งค่า client ให้ชี้ไปที่คำสั่ง `voxel-forge-mcp` ที่ติดตั้งไว้

### Cursor (`~/.cursor/mcp.json`)

```json
"VoxelForge": {
  "command": "voxel-forge-mcp",
  "args": []
}
```

### Claude Desktop

```json
{
  "mcpServers": {
    "VoxelForge": {
      "command": "voxel-forge-mcp",
      "args": []
    }
  }
}
```

บน Windows ยังใช้ตัวห่อ `run-mcp.bat` จาก checkout ได้เพื่อความสะดวก โดย
มันเรียก entry point ตัวเดียวกันที่ติดตั้งไว้ผ่าน
`uv run voxel-forge-mcp` ไม่ได้รันไฟล์ใน `src/` โดยตรง

รีสตาร์ต client แล้วตรวจว่าแผง MCP แสดง `VoxelForge` เป็น connected

### การทำงานแบบ headless

โดยค่าเริ่มต้น server ไม่ bind socket ใด ๆ — editor bridge จะเริ่มทำงาน
เมื่อมีการเรียก `voxelforge_launch_editor` เท่านั้น หากต้องการให้ bridge
เปิด listener ทันที ให้รัน `voxel-forge-mcp --bridge` หรือกำหนด
`VOXELFORGE_BRIDGE=1` วิธีนี้ทำให้ server ปลอดภัยสำหรับสภาพแวดล้อมแบบ
headless และ sandbox เช่น continuous integration

## Desktop app (ไม่ต้องใช้เบราว์เซอร์)

### การรัน

หลังติดตั้งพร้อม extra `desktop` (ดูหัวข้อ "การติดตั้ง"):

```bash
voxel-forge
```

หรือรันจาก checkout หลังทำ `uv sync --extra desktop`:

```bash
uv run voxel-forge
```

บน Windows `run-desktop.bat` ห่อคำสั่งเดียวกันไว้

### Build เป็น .exe (Windows)

```powershell
.\build-desktop.bat
```

ได้ไฟล์ที่ `dist\VoxelForge\VoxelForge.exe` — ดับเบิลคลิกเปิดได้เลย ไม่ต้อง
ติดตั้ง Python และไม่ต้องมีเบราว์เซอร์

### ฟีเจอร์ Desktop

- เปิด/บันทึก scene (JSON)
- Import `.vox` — export `.obj` (merged), `.vox` และ Roblox Luau
- Create → Build Tree (resolution 1–8)
- 3D view แบบ native (Qt3D) — หมุนกล้องด้วยเมาส์ปุ่มกลาง

MCP สำหรับ AI ยังใช้แยกกัน (บน Windows คือ `run-mcp.bat`) — สร้าง scene ผ่าน
AI แล้วเปิดใน desktop app จาก `~/.voxel-forge/scenes/`
(บน Windows: `%USERPROFILE%\.voxel-forge\scenes\`)

## Web editor (ทางเลือก)

editor ให้บริการโดย [Bun](https://bun.sh) และถูกรวมมาใน wheel ที่ติดตั้งแล้ว
ดังนั้น `voxelforge_launch_editor` จึงเปิดได้โดยไม่ต้องมี checkout โดย MCP
server จะเป็นผู้ดูแลโปรเซส Bun นั้น ตัว editor bind พอร์ตแบบ **ephemeral**
และรายงานพอร์ตนั้นเป็น event `listening` แบบมีโครงสร้างทาง stdout ทำให้
`voxelforge_launch_editor` คืน URL ที่ได้และเปิดในเบราว์เซอร์ให้ได้

หากต้องการรัน editor ด้วยตัวเองจาก checkout:

```bash
cd editor
bun install
bun run dev
```

บน Windows `run-editor.bat` ห่อคำสั่งชุดเดียวกันไว้ dev server แบบแยกนี้ก็
bind พอร์ต ephemeral เป็นค่าเริ่มต้นเช่นกัน หากต้องการใช้พอร์ตที่ bridge
ลงทะเบียนเป็น allowed origin ไว้ล่วงหน้าสำหรับกรณีนี้ ให้กำหนด
`VOXELFORGE_EDITOR_PORT=5173`

editor จะ sync สองทางกับ MCP ผ่าน WebSocket การสร้างหรือแก้ scene ผ่าน MCP
จะส่งไปยัง browser และการวางหรือลบ voxel ใน editor จะอัปเดต scene ฝั่ง MCP
ด้วย ส่วน bridge ก็ bind พอร์ต WebSocket และ HTTP แบบ ephemeral เช่นกัน โดย
`voxelforge_launch_editor` จะรายงานทั้งสองพอร์ต มีเพียงคำสั่งแบบแยก
`voxel-forge-bridge` เท่านั้นที่ใช้พอร์ตคงที่ 8765 (WebSocket) และ 8766
(HTTP) เป็นค่าเริ่มต้น และทั้งคู่รับ `--ws-port` กับ `--http-port` ได้

ทั้ง web editor และ bridge bind อยู่ที่ loopback (`127.0.0.1`) จึงเปิดจาก
เครื่องนี้เท่านั้น ไม่เปิดให้เครื่องอื่นในเครือข่ายเข้าถึง

### การสร้างผ่าน AI

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

### เปิดผลลัพธ์ใน Goxel

Export `.vox` แล้วเปิดใน Goxel หรือ MagicaVoxel:

```text
~/.voxel-forge/exports/my_house.vox
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
| `voxelforge_export_vox` | ส่งออก `.vox` |
| `voxelforge_export_obj` | ส่งออก `.obj` |
| `voxelforge_import_vox` | นำเข้า `.vox` |
| `voxelforge_launch_editor` | เปิด web editor |
| `voxelforge_save` / `voxelforge_load` | บันทึก/โหลด scene |

## โฟลเดอร์ข้อมูล

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
| Export | `.vox`, `.obj` | Luau → Roblox |

ทั้งสองใช้เสริมกันได้ และ Cursor เปิด MCP server ทั้งสองตัวพร้อมกันได้

## สัญญาอนุญาต

MIT — ดู [LICENSE](LICENSE) ลิขสิทธิ์ thanakon228 ส่วน Goxel เองเป็น GPL-3.0
([โครงการ Goxel](https://github.com/guillaumechereau/goxel)) และไม่มีโค้ด
ของ Goxel ถูกนำมาใช้ที่นี่
