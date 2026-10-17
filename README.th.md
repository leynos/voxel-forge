# VoxelForge

**VoxelForge** คือ voxel editor ที่ได้แรงบันดาลใจจาก
[Goxel](https://github.com/guillaumechereau/goxel) พร้อม **MCP bridge** ให้
AI อย่าง Cursor และ Claude Desktop สร้างและแก้โมเดล 3D ได้โดยตรง

> VoxelForge เป็น soft fork ของ
> [`thanakon228/voxel-forge`](https://github.com/thanakon228/voxel-forge) ซึ่ง
> ใช้สัญญาอนุญาต MIT เช่นเดียวกับ repository นี้
>
> VoxelForge **ไม่ใช่** fork ของ Goxel ตัว Goxel เองเป็น GPL-3.0 ส่วน
> VoxelForge เป็น implementation อิสระที่ออกแบบ MCP-first และไม่มีซอร์สโค้ด C
> ของ Goxel ทั้งสองทำงานร่วมกันผ่านรูปแบบไฟล์ที่อ่านและเขียนเหมือนกัน คือ
> `.vox` (MagicaVoxel) และ `.obj` (Wavefront)
>
> [`docs/provenance.md`](docs/provenance.md) บันทึกการตรวจสอบประวัติซอร์ส
> ที่รองรับข้อกล่าวอ้างข้างต้น ระบุสิ่งที่การตรวจสอบนี้ยังพิสูจน์ไม่ได้ และแยก
> หลักฐานเรื่องความสอดคล้องของรูปแบบไฟล์ออกจากข้อกล่าวอ้างเรื่องผู้เขียน
> [`docs/fork-and-interface-boundary.md`](docs/fork-and-interface-boundary.md)
> ระบุความหมายของขอบเขตนี้สำหรับผู้ที่นำโปรเจกต์ไปใช้

## ฟีเจอร์

| ฟีเจอร์ | รายละเอียด |
| --- | --- |
| 24-bit RGB | พาเลตสีเต็ม |
| Layers | หลาย layer เหมือน Goxel |
| Export | `.vox` (MagicaVoxel), `.obj` (Wavefront) |
| Import | `.vox` จาก Goxel / MagicaVoxel |
| Web Editor | Three.js 3D — คลิกวาง/ลบ voxel |
| MCP | เชื่อม Cursor, Claude และ client อื่น ๆ |

## การติดตั้ง

VoxelForge ติดตั้งเป็น Python tool ทั่วไปได้บน Linux, macOS และ Windows
โดยแนะนำให้ใช้ [uv](https://docs.astral.sh/uv/):

```bash
uv tool install git+https://github.com/leynos/voxel-forge
```

คำสั่งนี้ติดตั้ง console script สามรายการลงใน `PATH`:

| คำสั่ง | หน้าที่ |
| --- | --- |
| `voxel-forge-mcp` | MCP server ผ่าน stdio (ช่องทางหลัก) |
| `voxel-forge-bridge` | WebSocket/HTTP bridge แยกสำหรับ web editor |
| `voxel-forge` | Native desktop app (ต้องติดตั้ง `desktop` extra) |

หากต้องการ desktop app ให้ติดตั้ง extra เพิ่ม:

```bash
uv tool install 'voxel-forge[desktop] @ git+https://github.com/leynos/voxel-forge'
```

หากทำงานจาก checkout:

```bash
git clone https://github.com/leynos/voxel-forge
cd voxel-forge
uv sync            # add --extra desktop for the desktop app
uv run voxel-forge-mcp
```

## เชื่อมต่อ MCP client

กำหนด client ให้เรียกคำสั่ง `voxel-forge-mcp` ที่ติดตั้งไว้

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

บน Windows ยังใช้ wrapper `run-mcp.bat` จาก checkout ได้เพื่อความสะดวก โดย
wrapper เรียก entry point เดียวกันผ่าน `uv run voxel-forge-mcp` และไม่เรียก
ไฟล์ใน `src/` โดยตรง

ทดสอบคำสั่งเดียวกับที่ client เรียกได้จาก terminal:

```bash
voxel-forge-mcp
```

คำสั่งนี้เรียก console script ที่ติดตั้งไว้ จึงจะแสดงปัญหาเหมือนที่ client
พบหากไม่มีคำสั่งอยู่ใน `PATH` ส่วนการทำงานจาก checkout ใช้
`uv run voxel-forge-mcp` เพื่อทดสอบ environment ของโปรเจกต์

หลังแก้การตั้งค่า ให้เริ่ม client ใหม่และตรวจว่า MCP panel แสดงว่าเชื่อมต่อ
กับ `VoxelForge` แล้ว

### การทำงานแบบ headless

โดยค่าเริ่มต้น server จะไม่ผูกพอร์ตใด ๆ bridge ของ editor จะเริ่มทำงานเมื่อมี
การเรียก `voxelforge_launch_editor` เท่านั้น หากต้องการให้ตัว listener ของ
bridge เริ่มทำงานทันที ให้รัน `voxel-forge-mcp --bridge` หรือตั้งค่า
`VOXELFORGE_BRIDGE=1` ด้วยเหตุนี้ server จึงปลอดภัยสำหรับสภาพแวดล้อมแบบ
headless และ sandbox อย่างเช่น continuous integration

## Desktop App (ไม่ใช้เบราว์เซอร์)

### เปิดใช้งาน

หลังติดตั้ง `desktop` extra (ดู [การติดตั้ง](#การติดตั้ง)):

```bash
voxel-forge
```

หรือจาก checkout หลังรัน `uv sync --extra desktop`:

```bash
uv run voxel-forge
```

บน Windows ใช้ `run-desktop.bat` เพื่อเรียกคำสั่งเดียวกันได้

### สร้างไฟล์ .exe (Windows)

```powershell
.\build-desktop.bat
```

ไฟล์อยู่ที่ `dist\VoxelForge\VoxelForge.exe` — ดับเบิลคลิกเปิดได้โดยไม่ต้องมี
Python หรือเบราว์เซอร์

### ฟีเจอร์ Desktop

- เปิด/บันทึก scene (JSON)
- Import `.vox` / Export `.obj` (merged), `.vox`, Roblox Luau
- Create → Build Tree (resolution 1–8)
- มุมมอง 3D แบบ native (Qt3D) — หมุนกล้องด้วยเมาส์กลาง

MCP สำหรับ AI ยังทำงานแยกผ่าน `voxel-forge-mcp` — สร้าง scene ผ่าน AI แล้ว
เปิดใน Desktop จาก `~/.voxel-forge/scenes/` (Windows:
`%USERPROFILE%\.voxel-forge\scenes\`)

---

## Web Editor (ทางเลือก)

```bash
cd editor
bun install
bun run dev
```

Web Editor ให้บริการผ่าน [Bun](https://bun.sh) และถูกรวมอยู่ใน wheel ที่ติดตั้ง
แล้ว ทำให้ `voxelforge_launch_editor` ใช้งานได้โดยไม่ต้องมี checkout
บน Windows ใช้ `run-editor.bat` เพื่อเรียกคำสั่งเดียวกันได้

เมื่อเรียก `voxelforge_launch_editor` จาก MCP client ระบบจะเปิด editor และ
รายงาน URL ที่ใช้งานจริงให้ทราบ สำหรับการพัฒนาด้วยตนเอง คำสั่งด้านบนใช้
editor ที่ `http://127.0.0.1:5173` และ bridge แบบ standalone ใช้ WebSocket ที่
`ws://127.0.0.1:8765` เป็นค่าเริ่มต้น; การเรียกผ่าน MCP จะเลือกพอร์ตที่ว่างและ
ส่งค่าพอร์ตให้ editor โดยอัตโนมัติ การสร้างหรือแก้ scene ผ่าน MCP จะส่งไปยัง
browser และการวางหรือลบ voxel ใน editor จะอัปเดต scene ฝั่ง MCP ด้วย

ทั้ง web editor และ bridge bind อยู่ที่ loopback (`127.0.0.1`) จึงเข้าถึงได้
จากเครื่องนี้เท่านั้น และไม่เปิดให้เครื่องอื่นในเครือข่ายเข้าถึง

### 2. สร้างผ่าน AI

ตัวอย่าง prompt:

> สร้างบ้าน voxel แบบ Goxel ชื่อ my_house — ฐาน 8x8 สีเทา ตัวบ้าน 6x6x4 สีขาว
> หลังคาสามเหลี่ยมสีแดง

AI จะเรียก:

1. `voxelforge_create_scene`
2. `voxelforge_fill_box` / `voxelforge_place_many`
3. `voxelforge_preview` เพื่อตรวจรูปทรง
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

## เอกสาร

- [คู่มือผู้ใช้](docs/users-guide.md) — การติดตั้ง คำสั่งทั้งสาม การตั้งค่า MCP
  client, web editor และตำแหน่งจัดเก็บ scene กับ export
- [คู่มือนักพัฒนา](docs/developers-guide.md) — entry point, ขอบเขต launcher ของ
  desktop, ข้อกำหนดเครื่องมือ และ verification gates
- [ขอบเขต fork และ interface](docs/fork-and-interface-boundary.md) — สิ่งที่ fork
  รับประกัน และสัญญาเรื่องรูปแบบไฟล์และบรรทัดคำสั่งที่ผู้บริโภคพึ่งพาได้
- [ที่มา](docs/provenance.md) — โปรเจกต์ต้นทาง สถานะสัญญาอนุญาต การตรวจสอบ
  ประวัติซอร์สว่าประวัติของ repository นี้มีและไม่มีอะไร และข้อจำกัดของการ
  ตรวจสอบนั้น
- [ย้ายไป 0.2](docs/migration-0.2.md) — การเปลี่ยนแปลงคำสั่งติดตั้งในรุ่นนั้น
  และสิ่งที่ต้องปรับในการตั้งค่าเดิม
- [ย้ายไป 0.3](docs/migration-0.3.md) — การเปลี่ยน arguments ของ Python export
  และชนิดข้อมูล scene ที่บันทึกไว้ซึ่งวางแผนไว้สำหรับรุ่นนั้น

ทิศทางระยะยาวของโปรเจกต์ระบุไว้ใน [roadmap](docs/roadmap.md)

## สัญญาอนุญาต

MIT — โค้ด VoxelForge เป็นของผู้สร้าง

Goxel ต้นฉบับ: GPL-3.0
([โครงการ Goxel](https://github.com/guillaumechereau/goxel))
