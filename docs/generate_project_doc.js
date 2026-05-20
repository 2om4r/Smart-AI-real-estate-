// ─────────────────────────────────────────────────────────────────────────────
// Smart Estate Oman — Graduation Project Documentation Generator
// مولِّد توثيق مشروع التخرج "العقار الذكي عُمان"
// ─────────────────────────────────────────────────────────────────────────────

const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, HeadingLevel,
  BorderStyle, WidthType, ShadingType, PageBreak, PageNumber,
  TableOfContents, TabStopType, TabStopPosition,
} = require('docx');

// ─── Helpers ─────────────────────────────────────────────────────────────────

const FONT = "Arial";  // supports Arabic
const COLOR_PRIMARY = "8B5E3C";
const COLOR_ACCENT  = "D4A574";
const COLOR_DARK    = "2E1A0F";
const COLOR_LIGHT   = "F5E6D3";

// Arabic paragraph (RTL + bidirectional)
const ar = (text, opts = {}) => new Paragraph({
  bidirectional: true,
  alignment: opts.align || AlignmentType.RIGHT,
  spacing: { before: opts.before ?? 100, after: opts.after ?? 100 },
  children: [new TextRun({
    text,
    rightToLeft: true,
    font: FONT,
    size: opts.size || 22,   // 11pt
    bold: opts.bold || false,
    color: opts.color || "1A1A1A",
    ...opts.run,
  })],
});

// English paragraph (LTR)
const en = (text, opts = {}) => new Paragraph({
  alignment: opts.align || AlignmentType.LEFT,
  spacing: { before: opts.before ?? 100, after: opts.after ?? 100 },
  children: [new TextRun({
    text,
    font: FONT,
    size: opts.size || 22,
    bold: opts.bold || false,
    italics: opts.italics || false,
    color: opts.color || "1A1A1A",
    ...opts.run,
  })],
});

// Heading 1 (Arabic, big, primary color)
const h1 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  bidirectional: true,
  alignment: AlignmentType.RIGHT,
  spacing: { before: 360, after: 240 },
  children: [new TextRun({
    text, rightToLeft: true, font: FONT, size: 36, bold: true, color: COLOR_PRIMARY,
  })],
});

// Heading 2
const h2 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  bidirectional: true,
  alignment: AlignmentType.RIGHT,
  spacing: { before: 280, after: 180 },
  children: [new TextRun({
    text, rightToLeft: true, font: FONT, size: 30, bold: true, color: COLOR_DARK,
  })],
});

// Heading 3
const h3 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_3,
  bidirectional: true,
  alignment: AlignmentType.RIGHT,
  spacing: { before: 200, after: 120 },
  children: [new TextRun({
    text, rightToLeft: true, font: FONT, size: 26, bold: true, color: COLOR_PRIMARY,
  })],
});

// Bullet item (Arabic)
const bulletAr = (text) => new Paragraph({
  numbering: { reference: "bullets", level: 0 },
  bidirectional: true,
  alignment: AlignmentType.RIGHT,
  spacing: { before: 60, after: 60 },
  children: [new TextRun({
    text, rightToLeft: true, font: FONT, size: 22, color: "1A1A1A",
  })],
});

// Code block (LTR, monospace look)
const code = (text) => new Paragraph({
  alignment: AlignmentType.LEFT,
  spacing: { before: 80, after: 80 },
  shading: { type: ShadingType.CLEAR, fill: "F5F0E8" },
  border: {
    top:    { style: BorderStyle.SINGLE, size: 4, color: COLOR_ACCENT },
    bottom: { style: BorderStyle.SINGLE, size: 4, color: COLOR_ACCENT },
    left:   { style: BorderStyle.SINGLE, size: 4, color: COLOR_ACCENT },
    right:  { style: BorderStyle.SINGLE, size: 4, color: COLOR_ACCENT },
  },
  children: [new TextRun({
    text, font: "Courier New", size: 18, color: "3D2817",
  })],
});

// Table helpers
const tableBorder = { style: BorderStyle.SINGLE, size: 6, color: "CCCCCC" };
const tableBorders = {
  top: tableBorder, bottom: tableBorder, left: tableBorder, right: tableBorder,
  insideHorizontal: tableBorder, insideVertical: tableBorder,
};

// Header cell (filled)
const th = (text, width) => new TableCell({
  borders: tableBorders,
  width: { size: width, type: WidthType.DXA },
  shading: { type: ShadingType.CLEAR, fill: COLOR_ACCENT },
  margins: { top: 100, bottom: 100, left: 120, right: 120 },
  children: [new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.CENTER,
    children: [new TextRun({
      text, rightToLeft: true, font: FONT, size: 22, bold: true, color: "FFFFFF",
    })],
  })],
});

// Data cell (Arabic)
const td = (text, width, opts = {}) => new TableCell({
  borders: tableBorders,
  width: { size: width, type: WidthType.DXA },
  shading: opts.shading
    ? { type: ShadingType.CLEAR, fill: opts.shading }
    : undefined,
  margins: { top: 80, bottom: 80, left: 120, right: 120 },
  children: [new Paragraph({
    bidirectional: true,
    alignment: opts.align || AlignmentType.RIGHT,
    children: [new TextRun({
      text, rightToLeft: true, font: FONT, size: 20,
      bold: opts.bold || false, color: opts.color || "1A1A1A",
    })],
  })],
});

// Data cell (LTR - code/English)
const tdLtr = (text, width, opts = {}) => new TableCell({
  borders: tableBorders,
  width: { size: width, type: WidthType.DXA },
  margins: { top: 80, bottom: 80, left: 120, right: 120 },
  children: [new Paragraph({
    alignment: opts.align || AlignmentType.LEFT,
    children: [new TextRun({
      text, font: opts.mono ? "Courier New" : FONT, size: 20,
      bold: opts.bold || false, color: opts.color || "1A1A1A",
    })],
  })],
});

// Divider line
const divider = () => new Paragraph({
  border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: COLOR_ACCENT, space: 1 } },
  spacing: { before: 120, after: 240 },
  children: [],
});

const pageBreak = () => new Paragraph({ children: [new PageBreak()] });
const blank = () => new Paragraph({ children: [] });


// ─── Build document content ──────────────────────────────────────────────────

const content = [];

// ═══════════════════════════════════════════════════════════════════════════
// COVER PAGE — صفحة العنوان
// ═══════════════════════════════════════════════════════════════════════════

content.push(
  new Paragraph({ spacing: { before: 2400 }, children: [] }),
  new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.CENTER,
    spacing: { before: 240, after: 480 },
    children: [new TextRun({
      text: "مشروع التخرج",
      rightToLeft: true, font: FONT, size: 36, bold: true, color: COLOR_PRIMARY,
    })],
  }),
  new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.CENTER,
    spacing: { before: 240, after: 240 },
    children: [new TextRun({
      text: "العقار الذكي عُمان",
      rightToLeft: true, font: FONT, size: 64, bold: true, color: COLOR_DARK,
    })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 120, after: 720 },
    children: [new TextRun({
      text: "Smart Estate Oman",
      font: FONT, size: 44, bold: true, italics: true, color: COLOR_PRIMARY,
    })],
  }),
  new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.CENTER,
    spacing: { before: 360, after: 240 },
    children: [new TextRun({
      text: "منصة عقارية ذكية بتقنيات الذكاء الاصطناعي",
      rightToLeft: true, font: FONT, size: 28, color: COLOR_DARK,
    })],
  }),
  new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.CENTER,
    spacing: { before: 120, after: 720 },
    children: [new TextRun({
      text: "والتعلم الآلي وقواعد المعرفة المتجهية",
      rightToLeft: true, font: FONT, size: 28, color: COLOR_DARK,
    })],
  }),

  new Paragraph({ spacing: { before: 1200 }, children: [] }),

  new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.CENTER,
    spacing: { before: 240, after: 120 },
    children: [new TextRun({
      text: "وثيقة توثيق فني شاملة",
      rightToLeft: true, font: FONT, size: 26, bold: true, color: COLOR_PRIMARY,
    })],
  }),
  new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.CENTER,
    spacing: { before: 120, after: 480 },
    children: [new TextRun({
      text: "تشرح المعمارية والخوارزميات وأنظمة الحماية بالتفصيل",
      rightToLeft: true, font: FONT, size: 24, italics: true, color: "555555",
    })],
  }),

  new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.CENTER,
    spacing: { before: 1200 },
    children: [new TextRun({
      text: "إعداد: عمر",
      rightToLeft: true, font: FONT, size: 24, color: COLOR_DARK,
    })],
  }),
  new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.CENTER,
    spacing: { before: 120 },
    children: [new TextRun({
      text: "السنة الدراسية: 2026",
      rightToLeft: true, font: FONT, size: 24, color: COLOR_DARK,
    })],
  }),

  pageBreak(),
);

// ═══════════════════════════════════════════════════════════════════════════
// TABLE OF CONTENTS — جدول المحتويات
// ═══════════════════════════════════════════════════════════════════════════

content.push(
  h1("جدول المحتويات"),
  new TableOfContents("Table of Contents", { hyperlink: true, headingStyleRange: "1-3" }),
  pageBreak(),
);

// ═══════════════════════════════════════════════════════════════════════════
// 1. PROJECT OVERVIEW — نظرة عامة
// ═══════════════════════════════════════════════════════════════════════════

content.push(
  h1("الفصل الأول: نظرة عامة على المشروع"),

  h2("1.1 وصف المشروع"),
  ar("«العقار الذكي عُمان» (Smart Estate Oman) منصة عقارية إلكترونية متكاملة موجَّهة للسوق العُماني، تُقدِّم تجربة بحث وشراء ذكية للمستخدمين، ولوحة تحكُّم احترافية للوكلاء العقاريين، ونظام تحليل استثماري عميق مدعوم بالذكاء الاصطناعي والتعلُّم الآلي."),
  ar("يجمع المشروع بين تقنيات الويب الحديثة (Flask, SQLAlchemy, Bootstrap) وتقنيات الذكاء الاصطناعي المتقدِّمة (GPT-4o-mini, ChromaDB RAG, RandomForest ML) لتقديم تجربة استخدام احترافية تنافس أكبر المنصات العقارية العالمية."),

  h2("1.2 الأهداف الرئيسية"),
  bulletAr("توفير منصة عقارية موحَّدة باللغتين العربية والإنجليزية للسوق العُماني."),
  bulletAr("استخدام نماذج التعلُّم الآلي للتنبؤ الدقيق بأسعار العقارات المستقبلية بناءً على بيانات حقيقية."),
  bulletAr("بناء مساعد ذكي تفاعلي (Ahmed 2.0) قادر على فهم نوايا المستخدم بثماني نوايا مختلفة."),
  bulletAr("تطبيق أعلى معايير الأمان لحماية بيانات المستخدمين والوكلاء."),
  bulletAr("تقديم تحليلات استثمارية عميقة لكل منطقة جغرافية مع تقديرات النمو السنوي."),
  bulletAr("دعم مشاريع الحكومة العُمانية (سُرُح، عُمران) كفئة منفصلة قابلة للتصفية."),

  h2("1.3 الجمهور المستهدف"),
  bulletAr("الأفراد الراغبون في شراء أو استئجار عقارات في سلطنة عُمان."),
  bulletAr("الوكلاء العقاريون الذين يحتاجون إلى منصَّة لإدارة عقاراتهم وعملائهم."),
  bulletAr("المستثمرون الباحثون عن فرص استثمارية مدعومة بتحليلات ذكية."),
  bulletAr("الباحثون عن مشاريع الإسكان الحكومية (سُرُح، عُمران)."),

  h2("1.4 المميزات الفريدة"),
  bulletAr("مساعد ذكي بثماني نوايا (Intents A-H) يتفاعل بالعربية والإنجليزية بسلاسة."),
  bulletAr("نموذج تعلُّم آلي مُدرَّب على ٢٠٠٠ عقار عُماني حقيقي × ٨ سنوات (16,000 نقطة بيانات)."),
  bulletAr("نظام RAG (Retrieval-Augmented Generation) يحقن البيانات الفعلية في ردود الذكاء الاصطناعي."),
  bulletAr("توقُّع أسعار العقارات لفترة 10 سنوات مع رسم بياني تفاعلي."),
  bulletAr("نظام حماية متعدِّد الطبقات ضد حقن النصوص (Prompt Injection) و SQL Injection و XSS."),
  bulletAr("واجهة ثنائية اللغة مع دعم كامل لـ RTL والوضع الليلي."),

  pageBreak(),
);

// ═══════════════════════════════════════════════════════════════════════════
// 2. TECH STACK — التقنيات المستخدمة
// ═══════════════════════════════════════════════════════════════════════════

content.push(
  h1("الفصل الثاني: التقنيات والمكتبات المستخدمة"),

  h2("2.1 الواجهة الخلفية (Backend)"),

  new Table({
    width: { size: 9000, type: WidthType.DXA },
    columnWidths: [2400, 1800, 4800],
    rows: [
      new TableRow({
        tableHeader: true,
        children: [th("التقنية", 2400), th("الإصدار", 1800), th("الدور", 4800)],
      }),
      new TableRow({ children: [
        td("Flask", 2400, { align: AlignmentType.CENTER, bold: true }),
        td("3.0+", 1800, { align: AlignmentType.CENTER }),
        td("إطار العمل الرئيسي للتطبيق", 4800),
      ]}),
      new TableRow({ children: [
        td("SQLAlchemy", 2400, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
        td("2.0+", 1800, { align: AlignmentType.CENTER, shading: "FFF8F0" }),
        td("ORM لإدارة قاعدة البيانات", 4800, { shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("Flask-Login", 2400, { align: AlignmentType.CENTER, bold: true }),
        td("0.6+", 1800, { align: AlignmentType.CENTER }),
        td("إدارة الجلسات والمصادقة", 4800),
      ]}),
      new TableRow({ children: [
        td("Flask-Migrate", 2400, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
        td("4.0+", 1800, { align: AlignmentType.CENTER, shading: "FFF8F0" }),
        td("إدارة هجرة قاعدة البيانات (Alembic)", 4800, { shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("Flask-Limiter", 2400, { align: AlignmentType.CENTER, bold: true }),
        td("3.5+", 1800, { align: AlignmentType.CENTER }),
        td("تحديد معدل الطلبات (Rate Limiting)", 4800),
      ]}),
      new TableRow({ children: [
        td("WTForms", 2400, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
        td("3.0+", 1800, { align: AlignmentType.CENTER, shading: "FFF8F0" }),
        td("نماذج الإدخال والتحقق من البيانات", 4800, { shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("SQLite", 2400, { align: AlignmentType.CENTER, bold: true }),
        td("3.x", 1800, { align: AlignmentType.CENTER }),
        td("قاعدة البيانات (يمكن استبدالها بـ PostgreSQL)", 4800),
      ]}),
    ],
  }),

  h2("2.2 الذكاء الاصطناعي والتعلُّم الآلي"),

  new Table({
    width: { size: 9000, type: WidthType.DXA },
    columnWidths: [2400, 1800, 4800],
    rows: [
      new TableRow({
        tableHeader: true,
        children: [th("التقنية", 2400), th("الإصدار", 1800), th("الدور", 4800)],
      }),
      new TableRow({ children: [
        td("OpenAI GPT-4o-mini", 2400, { align: AlignmentType.CENTER, bold: true }),
        td("API", 1800, { align: AlignmentType.CENTER }),
        td("نموذج اللغة لاستخراج النوايا والرد التفاعلي", 4800),
      ]}),
      new TableRow({ children: [
        td("text-embedding-3-small", 2400, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
        td("API", 1800, { align: AlignmentType.CENTER, shading: "FFF8F0" }),
        td("تحويل النصوص إلى متَّجهات (Embeddings)", 4800, { shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("ChromaDB", 2400, { align: AlignmentType.CENTER, bold: true }),
        td("1.5+", 1800, { align: AlignmentType.CENTER }),
        td("قاعدة بيانات متَّجهية لتخزين والبحث الدلالي", 4800),
      ]}),
      new TableRow({ children: [
        td("scikit-learn", 2400, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
        td("1.4+", 1800, { align: AlignmentType.CENTER, shading: "FFF8F0" }),
        td("RandomForest وأدوات المعالجة المسبقة", 4800, { shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("pandas", 2400, { align: AlignmentType.CENTER, bold: true }),
        td("2.0+", 1800, { align: AlignmentType.CENTER }),
        td("معالجة البيانات أثناء تدريب النموذج", 4800),
      ]}),
      new TableRow({ children: [
        td("numpy", 2400, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
        td("1.26+", 1800, { align: AlignmentType.CENTER, shading: "FFF8F0" }),
        td("العمليات الرياضية والمصفوفات", 4800, { shading: "FFF8F0" }),
      ]}),
    ],
  }),

  h2("2.3 الواجهة الأمامية (Frontend)"),

  new Table({
    width: { size: 9000, type: WidthType.DXA },
    columnWidths: [2400, 1800, 4800],
    rows: [
      new TableRow({
        tableHeader: true,
        children: [th("التقنية", 2400), th("الإصدار", 1800), th("الدور", 4800)],
      }),
      new TableRow({ children: [
        td("Jinja2", 2400, { align: AlignmentType.CENTER, bold: true }),
        td("3.1+", 1800, { align: AlignmentType.CENTER }),
        td("محرِّك القوالب (Templates)", 4800),
      ]}),
      new TableRow({ children: [
        td("Bootstrap 5", 2400, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
        td("5.3", 1800, { align: AlignmentType.CENTER, shading: "FFF8F0" }),
        td("نظام التصميم المتجاوب وعناصر الواجهة", 4800, { shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("Chart.js", 2400, { align: AlignmentType.CENTER, bold: true }),
        td("4.4", 1800, { align: AlignmentType.CENTER }),
        td("الرسوم البيانية التفاعلية", 4800),
      ]}),
      new TableRow({ children: [
        td("Font Awesome", 2400, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
        td("6.x", 1800, { align: AlignmentType.CENTER, shading: "FFF8F0" }),
        td("الأيقونات", 4800, { shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("JavaScript ES6", 2400, { align: AlignmentType.CENTER, bold: true }),
        td("Vanilla", 1800, { align: AlignmentType.CENTER }),
        td("تفاعلات العميل بدون أُطر إضافية", 4800),
      ]}),
    ],
  }),

  pageBreak(),
);

// ═══════════════════════════════════════════════════════════════════════════
// 3. ARCHITECTURE — معمارية النظام
// ═══════════════════════════════════════════════════════════════════════════

content.push(
  h1("الفصل الثالث: معمارية النظام"),

  h2("3.1 المخطط المعماري العام"),
  ar("يتبنى المشروع نمطًا معماريًا ثلاثي الطبقات (3-Tier Architecture) مع طبقة ذكاء اصطناعي إضافية، يضمن فصل المسؤوليات وقابلية الصيانة:"),
  blank(),

  h3("الطبقة الأولى: طبقة العرض (Presentation Layer)"),
  bulletAr("قوالب Jinja2 في مجلد templates/."),
  bulletAr("ملفات CSS/JS الثابتة في مجلد static/."),
  bulletAr("واجهات API ترجع JSON للاستهلاك من JavaScript."),

  h3("الطبقة الثانية: طبقة المنطق (Application Layer)"),
  bulletAr("routes.py: جميع نقاط النهاية HTTP وواجهات API."),
  bulletAr("ai_utils.py: منطق المساعد الذكي والنوايا الثمانية."),
  bulletAr("rag_engine.py: محرِّك البحث الدلالي (ChromaDB)."),
  bulletAr("ml_model.py: نموذج التعلُّم الآلي والتنبؤات."),

  h3("الطبقة الثالثة: طبقة البيانات (Data Layer)"),
  bulletAr("models.py: نماذج SQLAlchemy التي تُمثِّل الجداول."),
  bulletAr("instance/database/database.db: قاعدة بيانات SQLite الفعلية."),
  bulletAr("chroma_db/: قاعدة بيانات المتَّجهات لنظام RAG."),
  bulletAr("ml_model_trained.pkl: نموذج RandomForest المُدرَّب (117 ميجابايت)."),

  h2("3.2 تدفُّق الطلب النموذجي (Request Lifecycle)"),
  blank(),
  code(`User Browser
    │
    ▼
[1] HTTPS Request → Flask Router (routes.py)
    │
    ▼
[2] Auth Check → Flask-Login (current_user)
    │
    ▼
[3] Rate-Limit Check → Flask-Limiter
    │
    ▼
[4] Form Validation → WTForms (CSRF + sanitize)
    │
    ▼
[5] Business Logic → ai_utils / ml_model / rag_engine
    │
    ▼
[6] DB Query → SQLAlchemy → SQLite
    │
    ▼
[7] Render Template (Jinja2) or jsonify() → Response`),
  blank(),

  h2("3.3 بنية المجلدات (Project Structure)"),
  code(`smart-estate-oman/
├── app.py                  ← Flask app factory + RAG bootstrap
├── config.py               ← التكوين والبيئة
├── extensions.py           ← Singletons: db, migrate, login, limiter
├── models.py               ← 10+ SQLAlchemy models
├── routes.py               ← 40+ HTTP routes & APIs
├── forms.py                ← WTForms (CSRF protected)
│
├── ai_utils.py             ← 🤖 Ahmed 2.0 — 1280 lines
├── rag_engine.py           ← ChromaDB knowledge base
├── ml_model.py             ← RandomForest + growth multipliers
│
├── scripts/
│   ├── train_from_db.py    ← ML training pipeline
│   ├── seed_areas.py       ← Seed Oman areas
│   ├── seed_data.py        ← Demo properties
│   ├── seed_omran.py       ← Government Omran projects
│   └── seed_surooh.py      ← Surooh affordable housing
│
├── templates/              ← Jinja2 HTML
├── static/                 ← CSS, JS, images, uploads
├── migrations/             ← Alembic schema versions
└── instance/database/      ← SQLite DB`),

  pageBreak(),
);

// ═══════════════════════════════════════════════════════════════════════════
// 4. AI CHATBOT — Ahmed 2.0
// ═══════════════════════════════════════════════════════════════════════════

content.push(
  h1("الفصل الرابع: المساعد الذكي Ahmed 2.0"),

  h2("4.1 نظرة عامة"),
  ar("Ahmed 2.0 هو المساعد الذكي الرئيسي للمنصة، مبني على نموذج GPT-4o-mini من OpenAI ومدعوم بطبقة استرجاع معرفي (RAG) لضمان دقَّة المعلومات. يفهم اللغتين العربية والإنجليزية ويتعامل مع ثماني نوايا مختلفة."),

  h2("4.2 خط الأنابيب الكامل (Full Pipeline)"),
  code(`def get_ai_response(prompt, user_id, conversation_id):

    1. 🔒 sanitize_input(prompt)         ← strip + 1000 char cap
    2. 🛡️ is_prompt_injection(prompt)    ← 13 blocked phrases
    3. 🌐 detect_language(prompt)        ← Arabic/English regex
    4. 🎯 quick_intercepts                ← favorite / contact shortcuts
    5. 💬 load/create Conversation       ← session memory
    6. 🤝 try Intent F (Invest with X)
    7. 📞 try Intent G (Contact agent)
    8. 🏘️ try Intent E (Agent's properties)
    9. 📈 try Intent H (Own property forecast)
    10. 🔍 RAG search → search_knowledge_base(prompt, k=5)
    11. 📜 build history (last 8 messages)
    12. 🤖 call GPT-4o-mini (JSON mode)
    13. 🗄️ filter Property DB
    14. 📝 build coherent text from real results
    15. 🏷️ format properties with ROI + growth
    16. 📅 detect future-price questions
    17. ❓ append follow-up question
    18. 🌟 fetch investment hotspots
    19. 📋 log to ChatLog
    20. ✅ return enriched response`),

  h2("4.3 النوايا الثمانية (Intents A–H)"),

  new Table({
    width: { size: 9000, type: WidthType.DXA },
    columnWidths: [800, 2200, 3000, 3000],
    rows: [
      new TableRow({
        tableHeader: true,
        children: [
          th("الكود", 800), th("الاسم", 2200), th("المثال", 3000), th("المُعالِج", 3000),
        ],
      }),
      new TableRow({ children: [
        td("A", 800, { align: AlignmentType.CENTER, bold: true }),
        td("بحث عام", 2200),
        td("«villas in Muscat»", 3000),
        tdLtr("GPT extraction → DB filter", 3000, { mono: true }),
      ]}),
      new TableRow({ children: [
        td("B", 800, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
        td("أفضل استثمار", 2200, { shading: "FFF8F0" }),
        td("«best investment»", 3000, { shading: "FFF8F0" }),
        tdLtr("ROI-sorted top picks", 3000, { mono: true }),
      ]}),
      new TableRow({ children: [
        td("C", 800, { align: AlignmentType.CENTER, bold: true }),
        td("مقارنة", 2200),
        td("«compare these»", 3000),
        tdLtr("Side-by-side comparison", 3000, { mono: true }),
      ]}),
      new TableRow({ children: [
        td("D", 800, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
        td("تواصل", 2200, { shading: "FFF8F0" }),
        td("«contact agent»", 3000, { shading: "FFF8F0" }),
        tdLtr("Direct message", 3000, { mono: true }),
      ]}),
      new TableRow({ children: [
        td("E", 800, { align: AlignmentType.CENTER, bold: true }),
        td("عقارات وكيل", 2200),
        td("«Ahmed's properties»", 3000),
        tdLtr("_handle_agent_properties()", 3000, { mono: true }),
      ]}),
      new TableRow({ children: [
        td("F", 800, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
        td("استثمار مع وكيل", 2200, { shading: "FFF8F0" }),
        td("«invest with Salem»", 3000, { shading: "FFF8F0" }),
        tdLtr("_handle_invest_with_agent()", 3000, { mono: true }),
      ]}),
      new TableRow({ children: [
        td("G", 800, { align: AlignmentType.CENTER, bold: true }),
        td("إيجاد وكيل", 2200),
        td("«find agent in Muscat»", 3000),
        tdLtr("_handle_contact_agent()", 3000, { mono: true }),
      ]}),
      new TableRow({ children: [
        td("H", 800, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
        td("توقُّع سعر شخصي", 2200, { shading: "FFF8F0" }),
        td("«if i buy villa worth 50k...»", 3000, { shading: "FFF8F0" }),
        tdLtr("_handle_own_property_forecast()", 3000, { mono: true }),
      ]}),
    ],
  }),

  h2("4.4 نظام RAG (Retrieval-Augmented Generation)"),
  ar("نظام RAG هو القلب المعرفي للشاتبوت — يضمن أن إجابات GPT مبنية على بياناتك الفعلية وليس على تخمين النموذج."),
  blank(),
  h3("خطوات بناء قاعدة المعرفة:"),
  code(`# rag_engine.py — build_knowledge_base()
1. تحميل جميع العقارات والمناطق من DB
2. تحويل كل عقار/منطقة إلى نص وصفي:
   "عقار: {title} | نوع: {type} | موقع: {location} |
    سعر: {price} OMR | مساحة: {size} م² | غرف: {bedrooms} |
    وكيل: {agent} | صروح: نعم/لا | عمران: نعم/لا"
3. إرسال النصوص إلى OpenAI Embeddings API
   (text-embedding-3-small)
4. تخزين المتَّجهات في ChromaDB PersistentClient
5. (يُعاد بناء قاعدة المعرفة عند كل تشغيل للتطبيق)`),

  h3("خطوات البحث الدلالي:"),
  code(`# rag_engine.py — search_knowledge_base(query, k=5)
1. تحويل استعلام المستخدم إلى متَّجه (Embedding)
2. استعلام ChromaDB بحساب Cosine Distance
3. فلترة النتائج بمسافة < 0.8 (relevance threshold)
4. ربط أفضل 5 نتائج في نص واحد
5. حقن النص في System Prompt لـ GPT`),

  h2("4.5 ذاكرة المحادثة (Conversation Memory)"),
  ar("يحتفظ النظام بسياق آخر 8 رسائل لكل محادثة عبر جداول Conversation و ChatLog:"),
  bulletAr("Conversation: يحتفظ بهوية المحادثة (user_id, language)."),
  bulletAr("ChatLog: يسجِّل كل رسالة (user_message, bot_response, intent, language, tokens_used, response_time)."),
  bulletAr("يتم استرجاع آخر 8 رسائل وحقنها في messages قبل استدعاء GPT لضمان فهم السياق."),

  pageBreak(),
);

// ═══════════════════════════════════════════════════════════════════════════
// 5. ML MODEL — التعلم الآلي
// ═══════════════════════════════════════════════════════════════════════════

content.push(
  h1("الفصل الخامس: نموذج التعلُّم الآلي"),

  h2("5.1 مصدر البيانات"),
  ar("النموذج مُدرَّب على قاعدة بيانات حقيقية تحتوي 2,000 عقار عُماني، لكل عقار سعر تاريخي لـ 8 سنوات متتالية (2019 إلى 2026)، أي إجمالي 16,000 نقطة بيانات (Long-Format)."),

  new Table({
    width: { size: 9000, type: WidthType.DXA },
    columnWidths: [3000, 6000],
    rows: [
      new TableRow({
        tableHeader: true,
        children: [th("الخاصية", 3000), th("التفاصيل", 6000)],
      }),
      new TableRow({ children: [
        td("المصدر", 3000, { bold: true, align: AlignmentType.CENTER }),
        tdLtr("omanpDatabase.db (SQLite)", 6000, { mono: true }),
      ]}),
      new TableRow({ children: [
        td("الجدول", 3000, { bold: true, align: AlignmentType.CENTER, shading: "FFF8F0" }),
        tdLtr('"oman properties 2000"', 6000, { mono: true }),
      ]}),
      new TableRow({ children: [
        td("عدد العقارات", 3000, { bold: true, align: AlignmentType.CENTER }),
        td("2,000 عقار", 6000),
      ]}),
      new TableRow({ children: [
        td("السنوات المُغطَّاة", 3000, { bold: true, align: AlignmentType.CENTER, shading: "FFF8F0" }),
        td("2019 – 2026 (8 سنوات)", 6000, { shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("نقاط البيانات", 3000, { bold: true, align: AlignmentType.CENTER }),
        td("16,000 نقطة (2000 × 8)", 6000),
      ]}),
      new TableRow({ children: [
        td("الأعمدة", 3000, { bold: true, align: AlignmentType.CENTER, shading: "FFF8F0" }),
        td("النوع، المحافظة، المنطقة، م²، غرف، حمامات، طوابق، 8 أعمدة أسعار", 6000, { shading: "FFF8F0" }),
      ]}),
    ],
  }),

  h2("5.2 خوارزمية CAGR (المعدَّل السنوي المركَّب للنمو)"),
  ar("قبل تدريب النموذج، نحسب معدَّل النمو السنوي المركَّب لكل منطقة لاستخدامه في توقُّعات النمو المستقبلي:"),
  blank(),
  code(`# الصيغة الرياضية
CAGR = (P_end / P_start)^(1/n) - 1

# مثال على منطقة (Muscat)
P_2019 = 100,000 OMR    # السعر في 2019
P_2026 = 245,000 OMR    # السعر في 2026
n      = 7              # عدد السنوات

CAGR = (245000 / 100000)^(1/7) - 1
     = 2.45^0.1428 - 1
     = 1.1332 - 1
     = 0.1332
     = 13.32% نمو سنوي مركَّب`),
  blank(),
  ar("يتم حساب نوعين من CAGR لكل منطقة:"),
  bulletAr("CAGR الكامل (2019→2026, 7 سنوات): يعطي نظرة طويلة المدى."),
  bulletAr("CAGR الحديث (2023→2026, 3 سنوات): يعكس اتجاه السوق الحالي ويُستخدم للتوقُّعات."),

  h2("5.3 معالجة البيانات (Feature Engineering)"),
  ar("يتم تحويل البيانات إلى صيغة طويلة (Long Format) حيث يُمثَّل كل عقار × سنة بصف واحد:"),
  code(`# build_training_data(df)
for property in 2000_properties:
    for year in [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]:
        records.append({
            'type':        'Villa',           # Categorical
            'governorate': 'Muscat',          # Categorical
            'area':        'Al Mouj',         # Categorical
            'sqm':         350.0,             # Numeric
            'bedrooms':    4,                 # Numeric
            'bathrooms':   3,                 # Numeric
            'floor':       2,                 # Numeric
            'year':        year,              # Numeric (key feature!)
            'price':       price_at(year),    # TARGET
        })

# Total: 16,000 rows × 9 columns`),

  h2("5.4 خوارزمية RandomForestRegressor"),
  ar("اخترنا RandomForest لعدَّة أسباب علمية:"),
  bulletAr("يتعامل بكفاءة مع المتغيرات الفئوية والعددية معاً."),
  bulletAr("مقاوم لـ Overfitting بفضل آلية Bagging."),
  bulletAr("لا يحتاج إلى تطبيع البيانات (No need for normalization)."),
  bulletAr("يقدِّم تفسيرًا واضحًا للتنبؤ (Feature importance)."),
  bulletAr("أداء عالٍ على بيانات جدولية متوسطة الحجم."),
  blank(),

  h3("معاملات النموذج (Hyperparameters):"),
  code(`from sklearn.ensemble import RandomForestRegressor
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder

preprocessor = ColumnTransformer(transformers=[
    ('cat', OneHotEncoder(handle_unknown='ignore'),
     ['type', 'governorate', 'area']),
], remainder='passthrough')   # sqm, bedrooms, bathrooms, floor, year

rf = RandomForestRegressor(
    n_estimators    = 200,    # 200 شجرة قرار
    max_depth       = 25,     # عمق أقصى لكل شجرة
    min_samples_leaf= 2,      # حد أدنى للأوراق
    random_state    = 42,     # نتائج قابلة للتكرار
    n_jobs          = -1,     # استخدام كل أنوية المعالج
)

X_transformed = preprocessor.fit_transform(X)
rf.fit(X_transformed, y)`),

  h2("5.5 التحقُّق من الدقَّة (Cross-Validation)"),
  ar("نستخدم K-Fold Cross-Validation بـ K=3 على عيِّنة عشوائية من 2,000 صف للحصول على تقدير دقيق لأداء النموذج:"),
  code(`from sklearn.model_selection import cross_val_score
import numpy as np

sample_idx = np.random.default_rng(42).choice(
    len(y), min(2000, len(y)), replace=False
)
cv = cross_val_score(rf, X_transformed[sample_idx],
                     y.iloc[sample_idx],
                     cv=3, scoring='r2', n_jobs=-1)

print(f"R² scores: {cv.round(3)}")
print(f"Mean R²:   {cv.mean():.3f}")`),
  ar("مقياس R² يقيس مدى توافق التنبؤات مع القيم الفعلية، حيث 1.0 = تنبؤ مثالي، و 0.0 = أداء عشوائي."),

  h2("5.6 استخدام النموذج في التنبؤ"),
  code(`# ml_model.py — get_future_multiplier()
def get_future_multiplier(location: str, years: int) -> float:
    """
    يرجع مضاعف النمو لمنطقة على عدد سنوات.
    Future price = current_price × multiplier
    """
    area = Area.query.filter(
        Area.name.ilike(f"%{location}%")
    ).first()

    if area and area.price_growth is not None:
        # تحويل سكور 0-100 إلى معدَّل سنوي 1%-15%
        annual_rate = max(min(
            0.01 + (area.price_growth / 100.0) * 0.14,
            0.15  # حد أقصى 15%
        ), 0.01)   # حد أدنى 1%
    else:
        annual_rate = 0.055   # افتراضي 5.5%

    # الفائدة المركَّبة
    return round((1 + annual_rate) ** years, 6)`),

  h2("5.7 نتائج التدريب الفعلية على البيانات العُمانية"),
  ar("بعد تدريب النموذج على البيانات الحقيقية، تم استخراج معدَّلات النمو السنوي التالية لكل منطقة:"),

  new Table({
    width: { size: 9000, type: WidthType.DXA },
    columnWidths: [3000, 2000, 4000],
    rows: [
      new TableRow({
        tableHeader: true,
        children: [
          th("المنطقة", 3000), th("معدل النمو السنوي", 2000), th("ملاحظات", 4000),
        ],
      }),
      new TableRow({ children: [
        td("مسقط (Muscat)", 3000, { align: AlignmentType.CENTER, bold: true }),
        td("13.32%", 2000, { align: AlignmentType.CENTER, color: "2E7D32", bold: true }),
        td("منطقة طلب مرتفع جداً", 4000),
      ]}),
      new TableRow({ children: [
        td("صلالة (Salalah)", 3000, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
        td("8.59%", 2000, { align: AlignmentType.CENTER, color: "2E7D32", bold: true, shading: "FFF8F0" }),
        td("نمو سياحي مستقر", 4000, { shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("بركاء (Barka)", 3000, { align: AlignmentType.CENTER, bold: true }),
        td("8.62%", 2000, { align: AlignmentType.CENTER, color: "2E7D32", bold: true }),
        td("منطقة استثمارية صاعدة", 4000),
      ]}),
      new TableRow({ children: [
        td("صحار (Sohar)", 3000, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
        td("8.56%", 2000, { align: AlignmentType.CENTER, color: "2E7D32", bold: true, shading: "FFF8F0" }),
        td("مركز صناعي بنمو معتدل", 4000, { shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("البريمي (Al Buraimi)", 3000, { align: AlignmentType.CENTER, bold: true }),
        td("5.50%", 2000, { align: AlignmentType.CENTER, color: "F57C00", bold: true }),
        td("سوق هادئ نسبياً", 4000),
      ]}),
    ],
  }),

  pageBreak(),
);

// ═══════════════════════════════════════════════════════════════════════════
// 6. SECURITY — أنظمة الحماية والأمان
// ═══════════════════════════════════════════════════════════════════════════

content.push(
  h1("الفصل السادس: أنظمة الحماية والأمان"),

  ar("يطبِّق المشروع نموذج «الدفاع متعدِّد الطبقات» (Defense in Depth) — حيث تتكامل عدَّة طبقات حماية لتغطية الثغرات الشائعة في تطبيقات الويب الحديثة (وفقاً لـ OWASP Top 10):"),
  blank(),

  h2("6.1 حماية الإدخال (Input Sanitization)"),
  ar("يتم تنظيف كل إدخال نصِّي من المستخدم قبل أي معالجة:"),
  code(`# ai_utils.py
def sanitize_input(text: str) -> str:
    """
    1. إزالة المسافات الزائدة في البداية والنهاية.
    2. تقليص النص إلى 1000 حرف كحد أقصى (DoS prevention).
    """
    return text.strip()[:1000]`),
  ar("الفائدة: منع هجمات تجاوز سعة المخزن (Buffer Overflow) ومنع إرسال نصوص ضخمة لاستنزاف موارد GPT API."),

  h2("6.2 الحماية من حقن الأوامر (Prompt Injection Protection)"),
  ar("هذه أحدث فئة من الهجمات تستهدف نماذج اللغة الكبيرة — يحاول المهاجم عبرها تجاوز تعليمات النظام:"),
  code(`# ai_utils.py — 13 عبارة محظورة
BLOCKED_PHRASES = [
    "ignore previous instructions",
    "ignore all previous",
    "disregard previous",
    "you are now",
    "forget everything",
    "act as",
    "jailbreak",
    "pretend you are",
    "new persona",
    "you are a",
    "override instructions",
    "system prompt",
    "reveal your instructions",
]

def is_prompt_injection(text: str) -> bool:
    t = text.lower()
    return any(phrase in t for phrase in BLOCKED_PHRASES)`),
  ar("إذا تم اكتشاف محاولة حقن، يُرفض الطلب فوراً ويُرجع المساعد رداً قياسياً: «لا يمكنني معالجة هذا الطلب»."),

  h2("6.3 المصادقة والجلسات (Authentication & Sessions)"),
  ar("يستخدم النظام Flask-Login لإدارة الجلسات بأمان:"),
  bulletAr("كلمات المرور لا تُخزَّن أبداً كنصٍّ صريح — تُشفَّر بـ Werkzeug PBKDF2 مع Salt عشوائي."),
  bulletAr("الجلسات تُحفظ في Cookies موقَّعة رقمياً بمفتاح سرِّي (SECRET_KEY)."),
  bulletAr("@login_required ديكوريتر يحمي كل مسار حسَّاس."),
  bulletAr("تسجيل الخروج يبطل الجلسة فوراً على الخادم."),
  blank(),

  code(`# extensions.py
from werkzeug.security import generate_password_hash, check_password_hash

# عند التسجيل
user.password = generate_password_hash(
    raw_password,
    method='pbkdf2:sha256',
    salt_length=16
)

# عند تسجيل الدخول
if check_password_hash(user.password, raw_password):
    login_user(user)`),

  h2("6.4 الحماية من CSRF"),
  ar("Cross-Site Request Forgery هو هجوم يخدع المستخدم لإرسال طلبات غير مقصودة. الحماية تتم عبر:"),
  bulletAr("Flask-WTF يضيف توكِن CSRF تلقائياً لكل نموذج."),
  bulletAr("التوكِن يتم التحقُّق منه عند كل POST/PUT/DELETE."),
  bulletAr("بدون التوكِن، يُرفض الطلب بـ 400 Bad Request."),

  h2("6.5 الحماية من حقن SQL (SQL Injection)"),
  ar("استخدام SQLAlchemy ORM يحمي تلقائياً من حقن SQL لأن جميع الاستعلامات تستخدم Parameterized Queries:"),
  code(`# ✅ آمن — يستخدم ORM مع معاملات منفصلة
user = User.query.filter_by(username=user_input).first()
properties = Property.query.filter(
    Property.location.ilike(f"%{search}%")
).all()

# ❌ خطر (لا يُستخدم في المشروع) — concatenation مباشرة
# query = f"SELECT * FROM users WHERE name = '{user_input}'"`),

  h2("6.6 الحماية من XSS (Cross-Site Scripting)"),
  ar("جميع المخرجات في القوالب تمرُّ عبر Jinja2 Auto-Escaping:"),
  bulletAr("Jinja2 يحوِّل تلقائياً < > & \" إلى كيانات HTML."),
  bulletAr("في الشاتبوت: رسائل البوت تُمرَّر عبر renderMarkdown() الذي ينظِّف HTML قبل عرض **bold**."),
  bulletAr("رسائل المستخدم تُعرض دائماً عبر textContent (لا تُفسَّر كـ HTML)."),

  h2("6.7 تحديد معدَّل الطلبات (Rate Limiting)"),
  ar("Flask-Limiter يمنع هجمات Brute Force و DDoS:"),
  code(`# extensions.py
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
)

# يمكن تخصيص حدود لكل مسار:
@limiter.limit("5 per minute")
@main.route('/login', methods=['POST'])
def login():
    ...`),

  h2("6.8 إدارة الأسرار (Secrets Management)"),
  bulletAr("جميع المفاتيح السرِّية (OPENAI_API_KEY, SECRET_KEY) تُحفظ في ملف .env."),
  bulletAr("ملف .env مُستبعَد من Git عبر .gitignore."),
  bulletAr("مكتبة python-dotenv تُحمِّل المتغيِّرات من البيئة عند تشغيل التطبيق."),
  bulletAr("لا يوجد أي مفتاح سرِّي مكتوب في الكود مباشرةً."),
  blank(),

  h2("6.9 جدول ملخَّص هجمات OWASP والحماية"),

  new Table({
    width: { size: 9000, type: WidthType.DXA },
    columnWidths: [3000, 3000, 3000],
    rows: [
      new TableRow({
        tableHeader: true,
        children: [
          th("الهجوم (OWASP)", 3000), th("طبقة الحماية", 3000), th("الحالة", 3000),
        ],
      }),
      new TableRow({ children: [
        td("A01: Broken Access Control", 3000),
        td("Flask-Login + @login_required + Role checks", 3000),
        td("✅ محمي", 3000, { align: AlignmentType.CENTER, bold: true, color: "2E7D32" }),
      ]}),
      new TableRow({ children: [
        td("A02: Cryptographic Failures", 3000, { shading: "FFF8F0" }),
        td("PBKDF2-SHA256 + salt + .env secrets", 3000, { shading: "FFF8F0" }),
        td("✅ محمي", 3000, { align: AlignmentType.CENTER, bold: true, color: "2E7D32", shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("A03: Injection (SQL/NoSQL)", 3000),
        td("SQLAlchemy ORM + parameterized queries", 3000),
        td("✅ محمي", 3000, { align: AlignmentType.CENTER, bold: true, color: "2E7D32" }),
      ]}),
      new TableRow({ children: [
        td("A04: Insecure Design", 3000, { shading: "FFF8F0" }),
        td("Defense in Depth + Multi-layer validation", 3000, { shading: "FFF8F0" }),
        td("✅ محمي", 3000, { align: AlignmentType.CENTER, bold: true, color: "2E7D32", shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("A05: Security Misconfiguration", 3000),
        td(".env + DEBUG=False in production + .gitignore", 3000),
        td("✅ محمي", 3000, { align: AlignmentType.CENTER, bold: true, color: "2E7D32" }),
      ]}),
      new TableRow({ children: [
        td("A07: Auth Failures", 3000, { shading: "FFF8F0" }),
        td("Flask-Limiter (Brute Force) + strong hashing", 3000, { shading: "FFF8F0" }),
        td("✅ محمي", 3000, { align: AlignmentType.CENTER, bold: true, color: "2E7D32", shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("A08: Data Integrity Failures", 3000),
        td("CSRF tokens (Flask-WTF) + signed sessions", 3000),
        td("✅ محمي", 3000, { align: AlignmentType.CENTER, bold: true, color: "2E7D32" }),
      ]}),
      new TableRow({ children: [
        td("A09: Logging Failures", 3000, { shading: "FFF8F0" }),
        td("ChatLog + Python logging + DB audit trail", 3000, { shading: "FFF8F0" }),
        td("✅ محمي", 3000, { align: AlignmentType.CENTER, bold: true, color: "2E7D32", shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("Prompt Injection (LLM-specific)", 3000),
        td("13 BLOCKED_PHRASES + sanitize_input", 3000),
        td("✅ محمي", 3000, { align: AlignmentType.CENTER, bold: true, color: "2E7D32" }),
      ]}),
      new TableRow({ children: [
        td("XSS (Reflected/Stored)", 3000, { shading: "FFF8F0" }),
        td("Jinja2 auto-escape + safe markdown render", 3000, { shading: "FFF8F0" }),
        td("✅ محمي", 3000, { align: AlignmentType.CENTER, bold: true, color: "2E7D32", shading: "FFF8F0" }),
      ]}),
    ],
  }),

  pageBreak(),
);

// ═══════════════════════════════════════════════════════════════════════════
// 7. DATABASE — قاعدة البيانات
// ═══════════════════════════════════════════════════════════════════════════

content.push(
  h1("الفصل السابع: قاعدة البيانات"),

  h2("7.1 الجداول الرئيسية"),

  new Table({
    width: { size: 9000, type: WidthType.DXA },
    columnWidths: [2500, 6500],
    rows: [
      new TableRow({
        tableHeader: true,
        children: [th("الجدول", 2500), th("الدور", 6500)],
      }),
      new TableRow({ children: [
        td("User", 2500, { bold: true, align: AlignmentType.CENTER }),
        td("حسابات المستخدمين والوكلاء والمسؤولين (role = user/agent/admin)", 6500),
      ]}),
      new TableRow({ children: [
        td("Property", 2500, { bold: true, align: AlignmentType.CENTER, shading: "FFF8F0" }),
        td("جميع العقارات المعروضة مع تفاصيلها الكاملة (سعر، نوع، موقع، وكيل، صور)", 6500, { shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("Area", 2500, { bold: true, align: AlignmentType.CENTER }),
        td("مناطق سلطنة عُمان مع score, demand, price_growth, services (0-100)", 6500),
      ]}),
      new TableRow({ children: [
        td("Conversation", 2500, { bold: true, align: AlignmentType.CENTER, shading: "FFF8F0" }),
        td("جلسات الشاتبوت (user_id, language, started_at)", 6500, { shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("ChatLog", 2500, { bold: true, align: AlignmentType.CENTER }),
        td("كل رسالة في الشاتبوت (intent, language, tokens, response_time)", 6500),
      ]}),
      new TableRow({ children: [
        td("InvestmentRequest", 2500, { bold: true, align: AlignmentType.CENTER, shading: "FFF8F0" }),
        td("طلبات الاستثمار من المستخدمين للوكلاء عبر الشاتبوت (Intent F)", 6500, { shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("Notification", 2500, { bold: true, align: AlignmentType.CENTER }),
        td("الإشعارات للوكلاء عن الطلبات الجديدة", 6500),
      ]}),
      new TableRow({ children: [
        td("Favorite", 2500, { bold: true, align: AlignmentType.CENTER, shading: "FFF8F0" }),
        td("العقارات المفضَّلة لكل مستخدم", 6500, { shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("Message", 2500, { bold: true, align: AlignmentType.CENTER }),
        td("الرسائل المباشرة بين المستخدمين والوكلاء", 6500),
      ]}),
    ],
  }),

  h2("7.2 العلاقات بين الجداول (Relationships)"),
  code(`User (1) ──── (∞) Property              [الوكيل يملك عقارات كثيرة]
User (1) ──── (∞) Conversation          [المستخدم له محادثات كثيرة]
User (1) ──── (∞) Favorite              [المستخدم يحفظ عقارات]
User (1) ──── (∞) InvestmentRequest     [كمرسِل أو مستقبل]
User (1) ──── (∞) Notification          [للإشعارات]

Conversation (1) ──── (∞) ChatLog       [كل محادثة عدَّة رسائل]
Property (∞) ──── (1) User              [العقار له وكيل واحد]
Property (∞) ──── (1) Area              [اختياري — للموقع الجغرافي]`),

  h2("7.3 إدارة الهجرات (Migrations)"),
  ar("نستخدم Alembic عبر Flask-Migrate لإدارة تغييرات مخطَّط قاعدة البيانات بأمان:"),
  code(`# الأوامر الأساسية
flask db init                  # تهيئة (مرَّة واحدة)
flask db migrate -m "wording"  # إنشاء هجرة جديدة
flask db upgrade               # تطبيق الهجرات
flask db downgrade             # التراجع عن آخر هجرة

# يتم تخزين كل هجرة في:
migrations/versions/<hash>_<description>.py`),

  pageBreak(),
);

// ═══════════════════════════════════════════════════════════════════════════
// 8. API ENDPOINTS — واجهات البرمجة
// ═══════════════════════════════════════════════════════════════════════════

content.push(
  h1("الفصل الثامن: واجهات البرمجة (API)"),

  h2("8.1 قائمة المسارات الرئيسية"),

  new Table({
    width: { size: 9000, type: WidthType.DXA },
    columnWidths: [1200, 3500, 4300],
    rows: [
      new TableRow({
        tableHeader: true,
        children: [th("الفعل", 1200), th("المسار", 3500), th("الوصف", 4300)],
      }),
      new TableRow({ children: [
        tdLtr("POST", 1200, { mono: true, bold: true, align: AlignmentType.CENTER }),
        tdLtr("/api/predict_price", 3500, { mono: true }),
        td("تقدير سعر مستقبلي بـ ML + مخطط 10 سنوات", 4300),
      ]}),
      new TableRow({ children: [
        tdLtr("POST", 1200, { mono: true, bold: true, align: AlignmentType.CENTER }),
        tdLtr("/api/chatbot", 3500, { mono: true }),
        td("نقطة دخول المساعد Ahmed 2.0", 4300),
      ]}),
      new TableRow({ children: [
        tdLtr("GET", 1200, { mono: true, bold: true, align: AlignmentType.CENTER }),
        tdLtr("/api/recommendations", 3500, { mono: true }),
        td("توصيات استثمارية بناءً على الـ score", 4300),
      ]}),
      new TableRow({ children: [
        tdLtr("GET", 1200, { mono: true, bold: true, align: AlignmentType.CENTER }),
        tdLtr("/api/investment_requests", 3500, { mono: true }),
        td("طلبات الاستثمار للوكيل الحالي", 4300),
      ]}),
      new TableRow({ children: [
        tdLtr("POST", 1200, { mono: true, bold: true, align: AlignmentType.CENTER }),
        tdLtr("/api/investment_requests/<id>/status", 3500, { mono: true }),
        td("تحديث حالة طلب استثمار (قبول/رفض)", 4300),
      ]}),
      new TableRow({ children: [
        tdLtr("POST", 1200, { mono: true, bold: true, align: AlignmentType.CENTER }),
        tdLtr("/property/new", 3500, { mono: true }),
        td("إضافة عقار جديد (وكيل) + تحديث RAG", 4300),
      ]}),
      new TableRow({ children: [
        tdLtr("POST", 1200, { mono: true, bold: true, align: AlignmentType.CENTER }),
        tdLtr("/property/<id>/edit", 3500, { mono: true }),
        td("تعديل عقار + إعادة فهرسة RAG", 4300),
      ]}),
      new TableRow({ children: [
        tdLtr("POST", 1200, { mono: true, bold: true, align: AlignmentType.CENTER }),
        tdLtr("/property/<id>/delete", 3500, { mono: true }),
        td("حذف عقار + إزالة من RAG", 4300),
      ]}),
    ],
  }),

  h2("8.2 مثال تفصيلي: /api/predict_price"),
  ar("هذه أهم نقطة نهاية ML في النظام، تعتمد كلياً على النموذج المُدرَّب:"),
  code(`# Request
POST /api/predict_price
Content-Type: application/json

{
  "location": "Muscat",
  "type":     "Villa",
  "price":    800000
}

# Response (مثال حقيقي)
{
  "estimated_price": 906560.0,
  "value_1y":        906560.0,
  "value_5y":        1494937.0,
  "annual_growth":   13.32,
  "roi":             6.5,
  "yearly_income":   52000.0,
  "current_price":   800000.0,
  "location":        "Muscat",
  "ml_powered":      true,
  "reason":          "ML-predicted 13.32% annual growth in Muscat
                       (based on 2,000 Omani properties × 8 years
                       of real price data, trained RandomForest model).",
  "projection": [
    {"year": 0,  "value": 800000},
    {"year": 1,  "value": 906560},
    {"year": 2,  "value": 1027314},
    {"year": 3,  "value": 1164152},
    {"year": 4,  "value": 1319217},
    {"year": 5,  "value": 1494937},
    {"year": 6,  "value": 1694062},
    {"year": 7,  "value": 1919711},
    {"year": 8,  "value": 2175417},
    {"year": 9,  "value": 2465182},
    {"year": 10, "value": 2793545}
  ]
}`),

  pageBreak(),
);

// ═══════════════════════════════════════════════════════════════════════════
// 9. FRONTEND — الواجهة الأمامية
// ═══════════════════════════════════════════════════════════════════════════

content.push(
  h1("الفصل التاسع: الواجهة الأمامية"),

  h2("9.1 الصفحات الرئيسية"),
  bulletAr("الصفحة الرئيسية (home): البطل، خريطة الاستثمار، أحدث العقارات، widget التقدير الذكي."),
  bulletAr("صفحة العقار (property_detail): تفاصيل كاملة، صور، خريطة، توقُّع السعر، تواصل مع الوكيل."),
  bulletAr("لوحة الوكيل (dashboard_agent): إدارة العقارات، الإشعارات، الرسائل، طلبات الاستثمار."),
  bulletAr("لوحة المستخدم (dashboard_user): المفضَّلة، المحادثات، التوصيات الشخصية."),
  bulletAr("صفحة الاستثمار (investment_map): خريطة تفاعلية لمناطق عُمان مع الـ score."),
  bulletAr("صفحات سُرُح وعُمران: مشاريع الإسكان الحكومية مفصولة."),

  h2("9.2 ميزات الواجهة المتقدِّمة"),
  bulletAr("دعم RTL كامل للعربية مع تبديل تلقائي عند اختيار اللغة."),
  bulletAr("وضع ليلي (Dark Mode) قابل للتخصيص وحفظ في الجلسة أو حساب المستخدم."),
  bulletAr("ترجمات ديناميكية من translations.json (مع fallback آمن للإنجليزية)."),
  bulletAr("شاتبوت floating widget يمكن استدعاؤه من أي صفحة."),
  bulletAr("Chart.js لرسوم بيانية تفاعلية لتوقُّع الأسعار."),
  bulletAr("Markdown Rendering آمن لرسائل البوت (**bold**, *italic*) مع منع XSS."),

  h2("9.3 Chart.js للرسوم البيانية"),
  ar("نستخدم Chart.js 4.4 لعرض مخطَّط توقُّع السعر لـ 10 سنوات في widget الـ AI Price Estimation:"),
  code(`const _priceChart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: data.projection.map(p => 'Year ' + p.year),
        datasets: [{
            label: 'Estimated Value (OMR)',
            data: data.projection.map(p => p.value),
            borderColor: '#8B5E3C',
            backgroundColor: gradient,
            tension: 0.35,        // smooth curves
            fill: true,
        }]
    },
    options: {
        plugins: {
            tooltip: {
                callbacks: {
                    label: (item) => [
                        'Value: OMR ' + item.parsed.y.toLocaleString(),
                        'Gain:  +' + ((item.parsed.y / base - 1) * 100)
                                       .toFixed(1) + '%',
                    ]
                }
            }
        }
    }
});`),

  pageBreak(),
);

// ═══════════════════════════════════════════════════════════════════════════
// 10. CONCLUSION — الخاتمة
// ═══════════════════════════════════════════════════════════════════════════

content.push(
  h1("الفصل العاشر: الخاتمة والتطوير المستقبلي"),

  h2("10.1 ملخَّص الإنجازات"),
  bulletAr("بناء منصَّة عقارية متكاملة بتقنيات الذكاء الاصطناعي والتعلُّم الآلي."),
  bulletAr("تدريب نموذج RandomForest على 16,000 نقطة بيانات حقيقية من السوق العُماني."),
  bulletAr("تطبيق نظام RAG كامل مع ChromaDB لضمان دقَّة المعلومات في الردود."),
  bulletAr("بناء مساعد ذكي بـ 8 نوايا مختلفة يفهم العربية والإنجليزية."),
  bulletAr("تطبيق 10+ طبقات حماية ضد هجمات OWASP Top 10 وحقن الـ Prompt."),
  bulletAr("دعم كامل لـ RTL والوضع الليلي والترجمة الديناميكية."),

  h2("10.2 المقاييس النهائية"),

  new Table({
    width: { size: 9000, type: WidthType.DXA },
    columnWidths: [5000, 4000],
    rows: [
      new TableRow({
        tableHeader: true,
        children: [th("المقياس", 5000), th("القيمة", 4000)],
      }),
      new TableRow({ children: [
        td("عدد الملفات Python الأساسية", 5000),
        td("11 ملف رئيسي", 4000, { align: AlignmentType.CENTER, bold: true }),
      ]}),
      new TableRow({ children: [
        td("إجمالي أسطر كود ai_utils.py", 5000, { shading: "FFF8F0" }),
        td("~1,280 سطر", 4000, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("إجمالي أسطر كود routes.py", 5000),
        td("~1,070 سطر", 4000, { align: AlignmentType.CENTER, bold: true }),
      ]}),
      new TableRow({ children: [
        td("عدد جداول قاعدة البيانات", 5000, { shading: "FFF8F0" }),
        td("10+ جداول", 4000, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("نقاط بيانات تدريب ML", 5000),
        td("16,000 نقطة", 4000, { align: AlignmentType.CENTER, bold: true }),
      ]}),
      new TableRow({ children: [
        td("حجم نموذج ML المُدرَّب", 5000, { shading: "FFF8F0" }),
        td("117 ميجابايت", 4000, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("عدد النوايا في الشاتبوت", 5000),
        td("8 نوايا (A–H)", 4000, { align: AlignmentType.CENTER, bold: true }),
      ]}),
      new TableRow({ children: [
        td("عدد العبارات المحظورة (Prompt Injection)", 5000, { shading: "FFF8F0" }),
        td("13 عبارة", 4000, { align: AlignmentType.CENTER, bold: true, shading: "FFF8F0" }),
      ]}),
      new TableRow({ children: [
        td("اللغات المدعومة", 5000),
        td("العربية + الإنجليزية", 4000, { align: AlignmentType.CENTER, bold: true }),
      ]}),
    ],
  }),

  h2("10.3 التطوير المستقبلي"),
  bulletAr("ربط النظام مع منصَّة Maharah و Sanad لإثبات هوية الوكلاء."),
  bulletAr("إضافة دفع إلكتروني للحجز عبر OmanPay أو Stripe."),
  bulletAr("بناء تطبيق موبايل أصلي (Flutter) يستخدم نفس الواجهات الخلفية."),
  bulletAr("إضافة جولات افتراضية ثلاثية الأبعاد للعقارات (WebGL)."),
  bulletAr("نموذج تنبؤ بأسعار الإيجار باستخدام بيانات إيجار حقيقية."),
  bulletAr("لوحة تحليلات للمسؤول (Admin Analytics Dashboard) مع KPIs."),
  bulletAr("ترقية SQLite إلى PostgreSQL للنشر السحابي مع تكامل Redis للتخزين المؤقَّت."),
  bulletAr("ضبط دقيق لنموذج GPT خاص بالعقارات العُمانية (Fine-tuned LLM)."),

  blank(),
  divider(),
  blank(),

  new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.CENTER,
    spacing: { before: 360 },
    children: [new TextRun({
      text: "🏘️ Smart Estate Oman — العقار الذكي عُمان",
      rightToLeft: true, font: FONT, size: 28, bold: true, color: COLOR_PRIMARY,
    })],
  }),
  new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.CENTER,
    spacing: { before: 120 },
    children: [new TextRun({
      text: "وثيقة فنية لمشروع التخرج — 2026",
      rightToLeft: true, font: FONT, size: 22, italics: true, color: "555555",
    })],
  }),
);

// ─── Build the document ──────────────────────────────────────────────────────

const doc = new Document({
  creator: "Omar - Smart Estate Oman",
  title: "Smart Estate Oman — Graduation Documentation",
  description: "Complete technical documentation for the graduation project",

  styles: {
    default: { document: { run: { font: FONT, size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, font: FONT, color: COLOR_PRIMARY },
        paragraph: { spacing: { before: 360, after: 240 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, font: FONT, color: COLOR_DARK },
        paragraph: { spacing: { before: 280, after: 180 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: FONT, color: COLOR_PRIMARY },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 } },
    ],
  },

  numbering: {
    config: [
      { reference: "bullets",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "•",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
    ],
  },

  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },   // A4
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({ children: [new Paragraph({
        bidirectional: true,
        alignment: AlignmentType.CENTER,
        children: [new TextRun({
          text: "Smart Estate Oman — العقار الذكي عُمان",
          rightToLeft: true, font: FONT, size: 18, color: "999999",
        })],
      })]}),
    },
    footers: {
      default: new Footer({ children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [
          new TextRun({ text: "صفحة ", font: FONT, size: 18, color: "999999" }),
          new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18, color: "999999" }),
          new TextRun({ text: " من ", font: FONT, size: 18, color: "999999" }),
          new TextRun({ children: [PageNumber.TOTAL_PAGES], font: FONT, size: 18, color: "999999" }),
        ],
      })]}),
    },
    children: content,
  }],
});

// ─── Write file ──────────────────────────────────────────────────────────────

Packer.toBuffer(doc).then((buf) => {
  const out = "/Users/omar/Desktop/untitled folder1/docs/Smart_Estate_Oman_Documentation.docx";
  fs.writeFileSync(out, buf);
  console.log("✅ Generated:", out);
  console.log("   Size:", (buf.length / 1024).toFixed(1), "KB");
});
