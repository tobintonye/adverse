(function () {
  const data = window.DASHBOARD_CHART_DATA || {
    monthlyLabels: [],
    monthlyValues: [],
    annualLabels: [],
    annualValues: [],
  };

  const monthlyLabels = data.monthlyLabels;
  const monthlyValues = data.monthlyValues;
  const annualLabels = data.annualLabels;
  const annualValues = data.annualValues;

  let monthlyChartInstance = null;
  let annualChartInstance = null;
  let chartsBuilt = false;

  function isLight() {
    return document.documentElement.classList.contains('light');
  }

  function themeColors() {
    return isLight()
      ? {
          tooltipBg: '#FFFFFF',
          tooltipTitle: '#111827',
          tooltipBody: '#6B7280',
          tooltipBorder: 'rgba(17,24,39,0.1)',
          gridColor: 'rgba(17,24,39,0.08)',
          tickColor: '#6B7280',
        }
      : {
          tooltipBg: '#131316',
          tooltipTitle: '#F2F2F5',
          tooltipBody: '#A9A9B2',
          tooltipBorder: 'rgba(255,255,255,0.1)',
          gridColor: 'rgba(255,255,255,0.06)',
          tickColor: '#A9A9B2',
        };
  }

  function tooltipOptions() {
    const c = themeColors();
    return {
      enabled: true,
      backgroundColor: c.tooltipBg,
      titleColor: c.tooltipTitle,
      titleFont: { family: 'Inter', weight: 'bold', size: 11 },
      bodyColor: c.tooltipBody,
      bodyFont: { family: 'Inter', size: 11 },
      borderColor: c.tooltipBorder,
      borderWidth: 1,
      padding: 10,
      displayColors: false,
      callbacks: {
        label: function (context) {
          let label = context.dataset.label || '';
          if (label) {
            label += ': ';
          }
          if (context.parsed.y !== null) {
            label += new Intl.NumberFormat('en-NG', {
              style: 'currency',
              currency: 'NGN',
            }).format(context.parsed.y);
          }
          return label;
        },
      },
    };
  }

  function buildSpendChart(canvasId, labels, values, datasetLabel) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 240);
    gradient.addColorStop(0, 'rgba(239, 68, 68, 0.65)');
    gradient.addColorStop(1, 'rgba(239, 68, 68, 0.02)');
    const c = themeColors();
    return new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: datasetLabel,
            data: values,
            backgroundColor: gradient,
            borderColor: 'rgba(239, 68, 68, 0.95)',
            borderWidth: 1.5,
            borderRadius: 6,
            hoverBackgroundColor: 'rgba(239, 68, 68, 1)',
            hoverBorderColor: '#ffffff',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: tooltipOptions(),
        },
        scales: {
          y: {
            grid: { color: c.gridColor },
            ticks: {
              color: c.tickColor,
              font: { family: 'Inter', size: 9 },
              callback: function (value) {
                return (
                  '₦' +
                  new Intl.NumberFormat('en-US', { notation: 'compact' }).format(
                    value
                  )
                );
              },
            },
            border: { dash: [4, 4] },
          },
          x: {
            grid: { display: false },
            ticks: {
              color: c.tickColor,
              font: { family: 'Inter', size: 9 },
            },
          },
        },
      },
    });
  }

  function ensureChartsBuilt() {
    if (chartsBuilt) return;
    chartsBuilt = true;
    monthlyChartInstance = buildSpendChart(
      'monthlyChart',
      monthlyLabels,
      monthlyValues,
      'Monthly Marketing Spend'
    );
    annualChartInstance = buildSpendChart(
      'annualChart',
      annualLabels,
      annualValues,
      'Annual Marketing Spend'
    );
  }

  function rebuildChartsForTheme() {
    if (!chartsBuilt) return;
    if (monthlyChartInstance) monthlyChartInstance.destroy();
    if (annualChartInstance) annualChartInstance.destroy();
    monthlyChartInstance = buildSpendChart(
      'monthlyChart',
      monthlyLabels,
      monthlyValues,
      'Monthly Marketing Spend'
    );
    annualChartInstance = buildSpendChart(
      'annualChart',
      annualLabels,
      annualValues,
      'Annual Marketing Spend'
    );
  }

  window.addEventListener('themechange', rebuildChartsForTheme);

  window.toggleSpendAnalytics = function () {
    const body = document.getElementById('spend-analytics-body');
    const chevron = document.getElementById('spend-analytics-chevron');
    if (!body) return;
    const opening = body.classList.contains('hidden');
    body.classList.toggle('hidden');
    if (chevron) chevron.style.transform = opening ? 'rotate(180deg)' : '';
    if (opening) {
      ensureChartsBuilt();
      if (monthlyChartInstance) monthlyChartInstance.resize();
      if (annualChartInstance) annualChartInstance.resize();
    }
  };

  window.switchChart = function (type) {
    const btnMonthly = document.getElementById('btn-monthly');
    const btnAnnual = document.getElementById('btn-annual');
    const containerMonthly = document.getElementById('container-monthly');
    const containerAnnual = document.getElementById('container-annual');
    const activeClass =
      'flex-1 sm:flex-initial px-3.5 py-1.5 text-xs font-bold transition-all duration-200 bg-white/10 text-white';
    const inactiveClass =
      'flex-1 sm:flex-initial px-3.5 py-1.5 text-xs font-bold transition-all duration-200 text-white/50 hover:text-white';

    if (type === 'monthly') {
      btnMonthly.className = activeClass;
      btnAnnual.className = inactiveClass;
      containerMonthly.classList.remove('hidden');
      containerAnnual.classList.add('hidden');
      if (monthlyChartInstance) monthlyChartInstance.resize();
    } else {
      btnAnnual.className = activeClass;
      btnMonthly.className = inactiveClass;
      containerAnnual.classList.remove('hidden');
      containerMonthly.classList.add('hidden');
      if (annualChartInstance) annualChartInstance.resize();
    }
  };
})();
