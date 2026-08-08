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

  const customTooltipOptions = {
    enabled: true,
    backgroundColor: '#131316',
    titleColor: '#F2F2F5',
    titleFont: { family: 'Inter', weight: 'bold', size: 11 },
    bodyColor: '#A9A9B2',
    bodyFont: { family: 'Inter', size: 11 },
    borderColor: 'rgba(255,255,255,0.1)',
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

  function buildSpendChart(canvasId, labels, values, datasetLabel) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 240);
    gradient.addColorStop(0, 'rgba(239, 68, 68, 0.65)');
    gradient.addColorStop(1, 'rgba(239, 68, 68, 0.02)');
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
          tooltip: customTooltipOptions,
        },
        scales: {
          y: {
            grid: { color: 'rgba(255,255,255,0.06)' },
            ticks: {
              color: '#A9A9B2',
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
              color: '#A9A9B2',
              font: { family: 'Inter', size: 9 },
            },
          },
        },
      },
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
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
  });

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