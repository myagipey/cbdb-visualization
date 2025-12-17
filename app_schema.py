import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network
import pandas as pd
import json
import sqlite3
import os
import re

# === 🔍 调试代码开始 (调试完后可以删除) ===
st.write("### 🔍 云端环境文件自检")
st.write(f"当前工作目录: `{os.getcwd()}`")
st.write("目录下的所有文件:")
st.write(os.listdir('.')) # 这会打印出服务器上所有的文件

if os.path.exists('cbdb_lite.db'):
    st.success("✅ 成功检测到 cbdb_lite.db")
else:
    st.error("❌ 未找到 cbdb_lite.db！请检查 GitHub 仓库是否上传，或文件名大小写是否一致。")

if os.path.exists('cbdb_codebook.xlsx'):
    st.success("✅ 成功检测到 cbdb_codebook.xlsx")
else:
    st.error("❌ 未找到 cbdb_codebook.xlsx！")
# === 🔍 调试代码结束 ===

# ================= 1. 页面配置 =================
st.set_page_config(
    page_title="CBDB 数据库架构全景",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stApp {background-color: #ffffff;} 
    section[data-testid="stSidebar"] {
        background-color: #f8f9fa;
        border-right: 1px solid #e9ecef;
    }
    /* 史料文本高亮样式 */
    .highlight-text {
        font-family: 'KaiTi', '楷体', serif;
        font-size: 20px;
        line-height: 1.8;
        background-color: #fcf8e3;
        padding: 25px;
        border-left: 6px solid #8d6e63;
        border-radius: 8px;
        color: #3e2723;
        margin-bottom: 25px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    .tag-person { background-color: #ffccbc; padding: 2px 6px; border-radius: 4px; border-bottom: 2px solid #ffab91; cursor: help; }
    .tag-loc { background-color: #b3e5fc; padding: 2px 6px; border-radius: 4px; border-bottom: 2px solid #81d4fa; cursor: help; }
    .tag-time { background-color: #ffe0b2; padding: 2px 6px; border-radius: 4px; border-bottom: 2px solid #ffcc80; cursor: help; }
    .tag-office { background-color: #c8e6c9; padding: 2px 6px; border-radius: 4px; border-bottom: 2px solid #a5d6a7; cursor: help; }
    .arrow-down { text-align: center; font-size: 28px; color: #bdbdbd; margin: 15px 0; font-weight: bold;}

    .stCodeBlock { border-radius: 8px; overflow: hidden; border: 1px solid #eee; }
</style>
""", unsafe_allow_html=True)

# ================= 2. 核心数据资产 & 字典库 (自动加载) =================
THEME = {
    "Core": "#FFCDD2", "Office": "#BBDEFB", "Kinship": "#C8E6C9",
    "Social": "#E1BEE7", "Entry": "#FFE0B2", "Text": "#D7CCC8", "Dict": "#F5F5F5", "Other": "#E0E0E0"
}

IGNORE_COLS = {"c_created_by", "c_created_date", "c_modified_by", "c_modified_date", "tts_sysno", "c_notes", "c_source",
               "c_pages"}


@st.cache_data
def load_codebook_metadata(excel_path):
    """
    从 cbdb_codebook.xlsx 自动提取表含义和字段含义
    """
    t_map = {}
    f_map = {}

    if not os.path.exists(excel_path):
        st.error(f"⚠️ 未找到字典文件: {excel_path}，无法加载详细中文释义。")
        return t_map, f_map

    try:
        xls = pd.ExcelFile(excel_path)

        # 1. 提取表含义 (从 TABLE_LIST sheet)
        # 根据你提供的 CSV，表名清单在 "TABLE_LIST" sheet 中
        if 'TABLE_LIST' in xls.sheet_names:
            df_tables = pd.read_excel(xls, 'TABLE_LIST')
            # 统一列名小写，防止大小写差异
            df_tables.columns = [c.lower() for c in df_tables.columns]

            for _, row in df_tables.iterrows():
                # 获取表名 (table_code) 和 中文解释 (explanation_cn)
                t_code = str(row.get('table_code', '')).strip().upper()
                t_cn = str(row.get('explanation_cn', '')).strip()
                t_en = str(row.get('explanation_en', '')).strip()

                # 优先使用中文，没有则用英文
                meaning = t_cn if t_cn and t_cn.lower() != 'nan' else t_en
                if t_code:
                    t_map[t_code] = meaning

        # 2. 提取字段含义 (遍历其他所有 sheet)
        # 假设每个 sheet 对应一张表，里面包含 column_code 和 meaning_cn
        for sheet_name in xls.sheet_names:
            if sheet_name == 'TABLE_LIST': continue  # 跳过目录页

            try:
                df_sheet = pd.read_excel(xls, sheet_name)
                df_sheet.columns = [c.lower() for c in df_sheet.columns]

                # 检查是否包含字段代码列
                if 'column_code' in df_sheet.columns:
                    for _, row in df_sheet.iterrows():
                        c_code = str(row.get('column_code', '')).strip()
                        c_cn = str(row.get('meaning_cn', '')).strip()
                        c_en = str(row.get('meaning_en', '')).strip()

                        meaning = c_cn if c_cn and c_cn.lower() != 'nan' else c_en

                        # 存入字典。注意：如果不同表有同名字段但含义不同，这里会覆盖。
                        # 通常 CBDB 中同名字段含义是一致的。
                        if c_code and meaning:
                            if c_code not in f_map:  # 避免重复读取覆盖，保留第一次读到的（或者去掉if以最后一次为准）
                                f_map[c_code] = meaning
            except Exception as e:
                # 某些 sheet 可能格式不对，跳过
                continue

    except Exception as e:
        st.error(f"读取 Excel 字典出错: {e}")

    return t_map, f_map


# --- 初始化加载 ---
CODEBOOK_PATH = 'cbdb_codebook.xlsx'  # 确保此文件在你的根目录下
TABLE_MEANING_MAP, FIELD_DESC_MAP = load_codebook_metadata(CODEBOOK_PATH)

# 如果读取失败（例如文件不存在），提供少量的默认值防止报错
if not TABLE_MEANING_MAP:
    TABLE_MEANING_MAP = {"BIOG_MAIN": "古代人物基本资料表(默认)"}


# ================= 补充：数据库结构分析逻辑 =================
def analyze_database_structure(db_path):
    """
    智能分析数据库结构 (依赖已加载的 TABLE_MEANING_MAP 和 FIELD_DESC_MAP)
    """
    # 如果数据库不存在，返回空结构，防止报错
    if not os.path.exists(db_path):
        return {}, [], {}, {}, []

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 获取所有表名
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    all_tables_raw = [row[0] for row in cursor.fetchall()]
    table_map = {t.upper(): t for t in all_tables_raw if not t.startswith("sqlite_")}

    nodes = {}
    edges = []
    schema_docs = {}
    field_info_for_js = {}
    col_to_tables = {}

    # --- 第一遍扫描：构建节点 (表) ---
    for table_real in table_map.values():
        table_upper = table_real.upper()

        # 简单的分组逻辑
        group = "Other"
        if "BIOG" in table_upper:
            group = "Core"
        elif any(x in table_upper for x in ["OFFICE", "POSTED", "APPT"]):
            group = "Office"
        elif "KIN" in table_upper:
            group = "Kinship"
        elif "ASSOC" in table_upper:
            group = "Social"
        elif "ENTRY" in table_upper:
            group = "Entry"
        elif "TEXT" in table_upper:
            group = "Text"
        elif any(x in table_upper for x in ["CODES", "DYNAST", "ADDR"]):
            group = "Dict"

        try:
            df_info = pd.read_sql(f"PRAGMA table_info({table_real})", conn)
        except:
            continue

        cols = df_info['name'].tolist()

        # 📝 使用从 Excel 加载的字典
        # 尝试大写匹配，如果没有再尝试原名匹配
        cn_meaning = TABLE_MEANING_MAP.get(table_upper, TABLE_MEANING_MAP.get(table_real, ""))
        if not cn_meaning: cn_meaning = "(未定义含义)"

        # 纯文本 Tooltip
        tooltip_text = f"【 {table_real} 】\n\n📝 含义: {cn_meaning}\n📊 列数: {len(cols)}"

        nodes[table_real] = {
            "label": table_real,
            "group": group,
            "title": tooltip_text
        }

        doc_rows = []
        for _, row in df_info.iterrows():
            fname = row['name']
            if fname not in IGNORE_COLS:
                if fname not in col_to_tables: col_to_tables[fname] = []
                col_to_tables[fname].append(table_real)

            # 📝 使用从 Excel 加载的字段字典
            desc = FIELD_DESC_MAP.get(fname, "")

            # 兜底策略：如果字典里没有，尝试简单的规则推断
            if not desc:
                if fname.endswith("_chn"):
                    desc = "中文名称"
                elif fname.endswith("_code"):
                    desc = "代码 (FK)"
                elif fname.endswith("_id"):
                    desc = "ID (FK)"
                elif fname.endswith("_year"):
                    desc = "年份"

            doc_rows.append([fname, row['type'], desc])

            if fname not in field_info_for_js:
                field_info_for_js[fname] = {"desc": desc or fname, "tables": []}
            field_info_for_js[fname]["tables"].append(table_real)

        schema_docs[table_real] = doc_rows

    # --- 第二遍扫描：建立连接 (基于命名规则) ---
    connected_tables = set()

    def add_edge(src, dst, label):
        if src == dst: return
        if (dst, src, label) not in edges:
            edges.append((src, dst, label))
            connected_tables.add(src)
            connected_tables.add(dst)

    for table_real in nodes.keys():
        cols = [r[0] for r in schema_docs[table_real]]

        for col in cols:
            if col in IGNORE_COLS: continue

            # 强规则连接
            if col == "c_personid" and "BIOG_MAIN" in table_map.values():
                add_edge(table_real, "BIOG_MAIN", col)
                continue
            if col == "c_dy" and "DYNASTIES" in table_map.values():
                add_edge(table_real, "DYNASTIES", col)
                continue

            # 命名推断连接 (例如 c_addr_id -> ADDR_CODES)
            if "_code" in col or "_id" in col:
                core_root = col.replace("c_", "").replace("_code", "").replace("_id", "").replace("index_", "").upper()
                if len(core_root) > 2:
                    candidates = [f"{core_root}_CODES", f"{core_root}_DATA", f"CODE_{core_root}"]
                    for cand in candidates:
                        if cand in table_map and table_map[cand] != table_real:
                            add_edge(table_real, table_map[cand], col)
                            break

    # --- 第三遍扫描：孤岛救援 (基于字段同名) ---
    orphan_tables = set(nodes.keys()) - connected_tables
    for orphan in orphan_tables:
        cols = [r[0] for r in schema_docs[orphan]]
        for col in cols:
            if col in IGNORE_COLS: continue
            if col in col_to_tables:
                others = col_to_tables[col]
                for other in others:
                    if other != orphan:
                        add_edge(orphan, other, col)
                        break
            if orphan in connected_tables: break

    conn.close()
    return nodes, edges, schema_docs, field_info_for_js, sorted(list(col_to_tables.keys()))


# --- 执行数据库分析 ---
DB_PATH = 'cbdb.db'
# 这里定义了后续侧边栏需要的 NODES_REAL 全局变量
NODES_REAL, EDGES_REAL, SCHEMA_DOCS_REAL, FIELD_INFO_JS, ALL_LINK_KEYS = analyze_database_structure(DB_PATH)
# ================= 3. 侧边栏 =================
with st.sidebar:
    st.markdown("# 🏛️ CBDB Project")
    mode = st.radio("模式:", ("架构拓扑图 (Schema)", "数据化原理 (Datafication)"))
    st.divider()

    if mode == "架构拓扑图 (Schema)":
        st.markdown("### 👁️ 视图控制")
        available_groups = sorted(list(set([n['group'] for n in NODES_REAL.values()]))) if NODES_REAL else []
        selected_keys = st.multiselect("展示模块:", available_groups, default=available_groups)
        spring_len = st.slider("连线长度", 50, 800, 300)


# ================= 4. 拓扑图逻辑 =================
# ================= 4. 拓扑图逻辑 (修复缩进版) =================
def render_schema_topology(selected_keys, spring_len):
    if not NODES_REAL: st.warning("⚠️ 未检测到 cbdb.db"); return

    # --- 内部函数：只负责生成 HTML 字符串 ---
    def create_graph_draggable(selected_keys, spring_len):
        net = Network(height="800px", width="100%", bgcolor="#ffffff", font_color="black", directed=False)
        node_degrees = {n: 0 for n in NODES_REAL}
        valid_edges = []
        for src, dst, label in EDGES_REAL:
            s_node = NODES_REAL.get(src)
            d_node = NODES_REAL.get(dst)
            if s_node and d_node and s_node['group'] in selected_keys and d_node['group'] in selected_keys:
                valid_edges.append((src, dst, label))
                node_degrees[src] += 1
                node_degrees[dst] += 1
        for node_id, info in NODES_REAL.items():
            if info["group"] not in selected_keys: continue
            size = 15
            if node_degrees[node_id] > 5: size = 25
            if node_degrees[node_id] > 20: size = 40
            net.add_node(node_id, label=info["label"], title=info["title"], color=THEME.get(info["group"], "#E0E0E0"),
                         shape="dot", size=size, borderWidth=1)
        for src, dst, label in valid_edges:
            try:
                net.add_edge(src, dst, title=label, color="#CFD8DC", width=1)
            except:
                pass
        net.set_options(
            f"""var options = {{ "physics": {{ "barnesHut": {{ "gravitationalConstant": -2000, "centralGravity": 0.3, "springLength": {spring_len}, "springConstant": 0.04, "damping": 0.09, "avoidOverlap": 0.1 }}, "minVelocity": 0.75 }}, "interaction": {{ "dragNodes": true, "hover": true, "zoomView": true }} }}""")
        path = "schema_v_real.html"
        net.save_graph(path)
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    # --- 主逻辑开始（注意缩进与 def create_graph_draggable 对齐）---

    # 1. 获取生成的原始 HTML 内容
    html_raw = create_graph_draggable(selected_keys, spring_len)

    # 2. UI 标题栏与下载按钮
    col_header, col_btn = st.columns([4, 1])
    with col_header:
        st.subheader("🕸️ 数据库架构交互拓扑图")
    with col_btn:
        st.download_button(
            label="📥 下载关系图 (HTML)",
            data=html_raw,
            file_name="cbdb_schema_graph.html",
            mime="text/html",
            help="下载生成的 HTML 文件，可以用浏览器直接打开，支持交互操作。"
        )

    # 3. 准备悬浮窗需要的变量
    # (这一行之前因为缩进错误导致未执行，现在修复了)
    options_html = "".join([f'<option value="{k}">{k}</option>' for k in ALL_LINK_KEYS])
    field_info_json = json.dumps(FIELD_INFO_JS, ensure_ascii=False)

    # 4. 构建 Overlay HTML
    overlay_html = f"""
    <div id="control-panel" style="position: absolute; top: 20px; left: 20px; z-index: 999; background: rgba(255, 255, 255, 0.95); border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.15); font-family: 'Segoe UI', Arial, sans-serif; border: 1px solid #eee; width: 320px;">
        <div id="control-panel-header" style="padding: 10px 15px; background: #f1f3f5; cursor: move; border-bottom: 1px solid #eee; font-weight: bold; color: #2c3e50;">🔦 字段透视镜 (Field Lens) <span style="float:right">✥</span></div>
        <div style="padding: 15px;">
            <select id="field-selector" onchange="updateGraphState()" style="width: 100%; padding: 6px; margin-bottom: 12px; border-radius: 4px; border: 1px solid #ddd;">
                <option value="">(点击连线或选择字段)</option>{options_html}</select>
            <div style="margin-bottom: 12px; display: flex; align-items: center;">
                <input type="checkbox" id="show-labels-check" onchange="updateGraphState()" style="margin-right: 8px; cursor: pointer;">
                <label for="show-labels-check" style="font-size: 13px; color: #555; cursor: pointer;">🔠 显示连线标签</label>
            </div>
            <div id="field-details-box" style="display: none; background: #f8f9fa; padding: 12px; border-radius: 6px; font-size: 13px; border: 1px solid #eee;">
                <div style="margin-bottom: 6px;">🏷️ <b>含义:</b> <span id="field-desc-text" style="color: #d32f2f;"></span></div>
                <div>🔗 <b>关联表数:</b> <span id="field-table-count" style="font-weight:bold;"></span></div>
            </div>
        </div>
    </div>
    """

    js_logic = f"""<script>
    const fieldInfo = {field_info_json};
    dragElement(document.getElementById("control-panel"));
    function dragElement(elmnt) {{ var pos1=0,pos2=0,pos3=0,pos4=0; document.getElementById(elmnt.id+"-header").onmousedown=dragMouseDown; function dragMouseDown(e){{ e=e||window.event;e.preventDefault();pos3=e.clientX;pos4=e.clientY;document.onmouseup=closeDragElement;document.onmousemove=elementDrag; }} function elementDrag(e){{ e=e||window.event;e.preventDefault();pos1=pos3-e.clientX;pos2=pos4-e.clientY;pos3=e.clientX;pos4=e.clientY;elmnt.style.top=(elmnt.offsetTop-pos2)+"px";elmnt.style.left=(elmnt.offsetLeft-pos1)+"px"; }} function closeDragElement(){{ document.onmouseup=null;document.onmousemove=null; }} }}
    function updateGraphState() {{
        var val = document.getElementById('field-selector').value;
        var showLabels = document.getElementById('show-labels-check').checked;
        var detailsBox = document.getElementById('field-details-box');
        var allEdges = network.body.data.edges.get();
        var updates = [];
        allEdges.forEach(function(e){{
            var isMatch = (e.title === val);
            var newColor, newWidth, newLabel;
            if(val === "") {{ newColor = '#CFD8DC'; newWidth = 1; }} else if(isMatch) {{ newColor = '#FF4500'; newWidth = 4; }} else {{ newColor = '#E0E0E0'; newWidth = 1; }}
            if (showLabels || isMatch) {{ newLabel = e.title; }} else {{ newLabel = " "; }}
            updates.push({{id:e.id, color: newColor, width: newWidth, label: newLabel}});
        }});
        network.body.data.edges.update(updates);
        if(val && fieldInfo[val]) {{
            detailsBox.style.display='block';
            document.getElementById('field-desc-text').innerText = fieldInfo[val].desc || "暂无说明";
            document.getElementById('field-table-count').innerText = fieldInfo[val].tables.length;
        }} else {{ detailsBox.style.display='none'; }}
    }}
    network.on("click", function(params) {{ if (params.edges.length > 0) {{ var edgeId = params.edges[0]; var edge = network.body.data.edges.get(edgeId); if (edge.title) {{ document.getElementById('field-selector').value = edge.title; updateGraphState(); }} }} else if (params.nodes.length === 0) {{ document.getElementById('field-selector').value = ""; updateGraphState(); }} }});
    </script>"""

    # 5. 渲染组件
    components.html(html_raw.replace('<body>', f'<body>{overlay_html}').replace('</body>', f'{js_logic}</body>'),
                    height=800)

    st.markdown("---")
    st.subheader("📖 数据库字典与字段解析")
    tab_list = sorted(list(SCHEMA_DOCS_REAL.keys()))
    if tab_list:
        sel = st.selectbox("查看表结构:", tab_list)
        st.dataframe(pd.DataFrame(SCHEMA_DOCS_REAL[sel], columns=["字段名", "数据类型", "含义说明"]),
                     use_container_width=True, hide_index=True)


# ================= 5. 数据化原理 (V11.1 核心聚合版) =================
def render_datafication_case_study():
    st.title("📜 从史料到数据库：历史人物的数据化之旅")
    st.markdown(
        "本模块以 **苏轼 (Su Shi, ID: 3767)** 为例，展示如何通过 SQL 的 `JOIN` 操作，将数据库中的数字 ID 还原为有意义的历史信息。")
    if not os.path.exists('cbdb.db'): st.warning("请上传 cbdb.db"); return
    conn = sqlite3.connect('cbdb.db')

    # 1. 文本展示
    st.header("1. 史料原文 (非结构化)")
    st.markdown("""
    <div class="highlight-text">
        <span class="tag-person" title="人物">苏轼</span>，字<span class="tag-person">子瞻</span>，<span class="tag-loc" title="地点">眉州眉山</span>人。……
        <span class="tag-time" title="时间">嘉祐二年</span>，<span class="tag-office" title="入仕/科举">试礼部</span>。……
        知<span class="tag-loc">徐州</span>。……既而<span class="tag-office">贬</span>……<span class="tag-loc">黄州</span>团练副使。
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div class="arrow-down">⬇️ 关联查询 (JOIN Operation) ⬇️</div>', unsafe_allow_html=True)

    # 2. 数据库表名探测
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    ts = {r[0].upper(): r[0] for r in cursor.fetchall()}

    def get(n):
        for x in n:
            if x in ts: return ts[x]
        return None

    col1, col2 = st.columns([1, 1.2])

    # --- 左侧：核心身份 (含籍贯、别名聚合) ---
    with col1:
        st.subheader("👤 核心身份 (BIOG_MAIN)")

        T_DYNASTY = get(["DYNASTIES"])
        T_ADDR_CODES = get(["ADDR_CODES", "CODE_ADDR"])
        T_ALT_DATA = get(["ALTNAME_DATA"])

        # 基础字段
        select_parts = [
            "B.c_personid AS [人物ID]",
            "B.c_name_chn AS [姓名]",
            "B.c_birthyear AS [生年]"
        ]
        join_parts = []
        group_by = ""

        # 连接朝代
        if T_DYNASTY:
            select_parts.append("D.c_dynasty_chn AS [朝代]")
            join_parts.append(f"LEFT JOIN {T_DYNASTY} D ON B.c_dy = D.c_dy")

        # 连接籍贯
        if T_ADDR_CODES:
            select_parts.append("A.c_name_chn AS [籍贯]")
            join_parts.append(f"LEFT JOIN {T_ADDR_CODES} A ON B.c_index_addr_id = A.c_addr_id")

        # ✨ 核心改动：连接别名并聚合 (一对多 -> 一对一字符串)
        if T_ALT_DATA:
            select_parts.append("GROUP_CONCAT(DISTINCT ALT.c_alt_name_chn) AS [别名/字号]")
            join_parts.append(f"LEFT JOIN {T_ALT_DATA} ALT ON B.c_personid = ALT.c_personid")
            group_by = "GROUP BY B.c_personid"
        else:
            select_parts.append("'未知' AS [别名/字号]")

        sql_bio = f"""SELECT 
    {', '.join(select_parts)}
FROM BIOG_MAIN B 
{'\n'.join(join_parts)}
WHERE B.c_personid = 3767
{group_by}"""

        st.code(sql_bio, "sql")
        try:
            st.dataframe(pd.read_sql(sql_bio, conn), hide_index=True)
        except:
            st.error("核心身份查询失败")

        st.divider()

        # --- 入仕记录 ---
        st.subheader("🎓 入仕记录 (ENTRY_DATA)")
        T_ENTRY_DATA = get(["ENTRY_DATA"])
        T_ENTRY_CODES = get(["ENTRY_CODES", "CODE_ENTRY"])
        T_NIAN_HAO = get(["NIAN_HAO"])  # 获取年号表

        if T_ENTRY_DATA and T_ENTRY_CODES:
            # 构建查询字段
            cols = [
                "E.c_year AS [西历]",
                "C.c_entry_desc_chn AS [入仕途径]",
                "E.c_age AS [年龄]"
            ]
            joins = [
                f"LEFT JOIN {T_ENTRY_CODES} C ON E.c_entry_code = C.c_entry_code"
            ]

            # 如果存在年号表，进行关联以显示“嘉祐二年”
            if T_NIAN_HAO:
                # 调整字段顺序，把年号放在最前面，呼应史料
                cols.insert(0, "N.c_nianhao_chn || ' ' || E.c_entry_nh_year || '年' AS [年号纪年]")
                joins.append(f"LEFT JOIN {T_NIAN_HAO} N ON E.c_nianhao_id = N.c_nianhao_id")

            # 组合 SQL：增加 AND E.c_year = 1057 精准定位嘉祐二年
            sql_entry = f"""SELECT 
            {', '.join(cols)}
        FROM {T_ENTRY_DATA} E
        {' '.join(joins)}
        WHERE E.c_personid = 3767 
          AND E.c_year = 1057"""  # <--- 关键修改：筛选嘉祐二年(1057)

            st.code(sql_entry, "sql")
            try:
                df_entry = pd.read_sql(sql_entry, conn)
                if df_entry.empty:
                    st.info("注：当前数据库中未找到嘉祐二年的特定记录，请检查 c_year 数据。")
                else:
                    st.dataframe(df_entry, hide_index=True)
            except Exception as e:
                st.error(f"入仕查询失败: {e}")
        else:
            st.info("未检测到入仕数据表。")

    # --- 右侧：任官履历 ---
    with col2:
        st.subheader("📜 任官履历 (OFFICE_DATA)")

        T_OFFICE_DATA = get(["POSTED_TO_OFFICE_DATA"])
        T_OFFICE_CODES = get(["OFFICE_CODES", "CODE_OFFICE"])
        T_ADDR_DATA = get(["POSTED_TO_ADDR_DATA"])
        T_ADDR_CODES = get(["ADDR_CODES", "CODE_ADDR"])

        select_clause = "P.c_firstyear AS [任职年份]"
        join_clause = ""

        if T_OFFICE_CODES:
            select_clause += ",\n    O.c_office_chn AS [官职名称]"
            join_clause += f"LEFT JOIN {T_OFFICE_CODES} O ON P.c_office_id = O.c_office_id\n"
        else:
            select_clause += ",\n    '未知' AS [官职名称]"

        if T_ADDR_DATA and T_ADDR_CODES:
            select_clause += ",\n    A.c_name_chn AS [任职地点]"
            join_clause += f"LEFT JOIN {T_ADDR_DATA} PA ON P.c_posting_id = PA.c_posting_id\n"
            join_clause += f"LEFT JOIN {T_ADDR_CODES} A ON PA.c_addr_id = A.c_addr_id"
        else:
            select_clause += ",\n    '[无地点]' AS [任职地点]"

        sql_office = f"""SELECT 
    {select_clause}
FROM {T_OFFICE_DATA} P
{join_clause}
WHERE P.c_personid = 3767
LIMIT 10"""

        st.code(sql_office, "sql")
        try:
            df = pd.read_sql(sql_office, conn)
            df.fillna("—", inplace=True)
            st.dataframe(df, hide_index=True, use_container_width=True)
        except:
            st.error("查询失败")

    conn.close()


# ================= 6. 入口 =================
if mode == "架构拓扑图 (Schema)":
    render_schema_topology(selected_keys, spring_len)
elif mode == "数据化原理 (Datafication)":

    render_datafication_case_study()
