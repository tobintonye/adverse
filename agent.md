# Advers Design System & UI Standards

This document serves as the design patterns and UI/UX standards reference for the **Advers Admin Panel**. Any edits or enhancements to the dashboard and associated pages must align with these guidelines to ensure a premium, modern, and cohesive user experience.

---

## 1. Color Palette

We utilize a dark-mode-first, high-contrast, premium interface. Accent colors are highly saturated, using gradients and transparency to blend seamlessly.

| Token | CSS/Tailwind Class | HSL / Hex | Usage |
| :--- | :--- | :--- | :--- |
| **Deep Background** | `bg-black` / `bg-[#030303]` | `#030303` | Global body background |
| **Surface Dark** | `bg-zinc-950` | `#09090b` | Sidebars, main container background |
| **Surface Card** | `bg-zinc-900/40` | `rgba(24, 24, 27, 0.4)` | Dashboard cards, feed containers |
| **Border Muted** | `border-zinc-800/60` | `rgba(39, 39, 42, 0.6)` | Low-contrast element borders |
| **Border Active** | `border-zinc-700/80` | `rgba(63, 63, 70, 0.8)` | Hovered cards, inputs, buttons |
| **Accent Red** | `text-red-500` / `bg-red-500` | `#ef4444` | Advers brand color, critical metrics, alerts |
| **Success Green** | `text-emerald-500` | `#10b981` | Online status, approved campaigns, normal states |
| **Warning Amber** | `text-amber-500` | `#f59e0b` | Pending review, verification alerts |

---

## 2. Design Language: Glassmorphism

To elevate the UI from flat dark mode to a premium dashboard, we employ **Glassmorphic surfaces** using background blurs, gradients, and fine borders.

### The Glass Card Pattern
All major dashboard elements must follow the Glass Card design:
- **Background**: Translucent surface (`bg-zinc-900/40` or `bg-zinc-900/50`).
- **Blur**: Medium-to-high backdrop filter (`backdrop-blur-md` or `backdrop-blur-lg`).
- **Border**: Fine, semi-transparent border (`border border-zinc-800/80`).
- **Hover Transition**: Smooth transform and border brightness shift.
- **Radial Glow**: Subtle radial background gradient showing on hover.

**Example HTML structure:**
```html
<div class="relative overflow-hidden bg-zinc-900/40 backdrop-blur-md border border-zinc-800/80 hover:border-zinc-700/80 rounded-xl p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_10px_30px_-15px_rgba(0,0,0,0.5)] group">
    <!-- Hover Radial Glow -->
    <div class="absolute inset-0 bg-gradient-to-br from-red-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
    
    <!-- Card Content -->
</div>
```

---

## 3. Typography & Hierarchy

We use Google Fonts' **Inter** as our core typeface for maximum readability on screens.

- **Primary Headings (`h1`, `h2`)**: `font-bold` or `font-semibold`, tracked slightly tight (`tracking-tight`), text color `text-white` or `text-zinc-100`.
- **Secondary Headings / Card Titles**: `text-xs` or `text-[10px]`, `font-bold` or `font-semibold`, uppercase, tracked wide (`tracking-widest`), text color `text-zinc-500`.
- **Metric Values**: `text-4xl` or `text-5xl`, `font-black` or `font-extrabold`, text color `text-white`.
- **Subtexts / Meta info**: `text-xs` or `text-[11px]`, text color `text-zinc-500` or `text-zinc-400`.

---

## 4. UI Components

### 4.1 KPI Cards
KPI cards must instantly communicate current status and importance:
1. **Visual State Indicator**: A pulsing dot or custom icon matching the state (e.g. Red for urgent items, Amber for warning/pending, Green for active/online).
2. **Dynamic Gradient Glows**: Hovering a KPI highlights it with its status color (e.g., Red glow for pending, Green glow for active).
3. **Progress Bar or Sparklines (Visual KPI)**: Add a visual representation (e.g. mini status bar or progress circle) representing the ratio of pending-to-total or status health.

### 4.2 Pending Submission Feed (Interactive List)
- **Grouping**: Group submissions logically (Advertisers, Ad Managers, Media, Campaigns) with a unified, interactive timeline or feed layout.
- **Card Design**: Submissions are structured as individual horizontal strips with hover highlights.
- **Visual Previews**: Media thumbnails must render with rounded corners, a dark container, and play/image icons depending on file type.
- **Direct Actions**: Verification/Review buttons must be accessible on hover/display, with clear accent borders (e.g., `hover:bg-zinc-850 hover:border-zinc-600`).

### 4.3 System Status (Progress Rings / Badges)
- Instead of a plain key-value list, status fields should utilize visual representations:
  - **Online Player boxes**: A glowing, pulsing indicator green container.
  - **Proportion Badges**: Show numbers inside structured pill badges with subtle backgrounds (e.g. `bg-zinc-800/50 text-zinc-300`).
  - **Progress Visuals**: Render progress bars indicating ratio (e.g., Online devices vs Total devices).

### 4.4 Quick Navigation
- Navigation items should feel tactile.
- Grid icons with simple hover transformations.
- Explicit visual indication when hovering.

---

## 5. Animations & Micro-Interactions

- **Hover Translation**: Cards float upwards slightly (`hover:-translate-y-1 duration-300`).
- **Pulse Indicators**: Status lights must pulse softly to feel "alive".
  ```css
  .status-pulse {
      animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  }
  @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: .4; transform: scale(0.92); }
  }
  ```
- **Fades & Hover Glows**: Background glows fade in smoothly over `300ms`.
