(function () {
    const dataEl = document.getElementById("dashboard-chart-data");
    const chartData = JSON.parse(dataEl.textContent);

    const monthlyLabels = chartData.monthlyLabels;
    const monthlyValues = chartData.monthlyValues;
    const annualLabels = chartData.annualLabels;
    const annualValues = chartData.annualValues;

    let monthlyChartInstance = null;
    let annualChartInstance = null;

    const TAB_ACTIVE = "flex-1 sm:flex-initial px-3.5 py-1.5 text-xs font-bold rounded-full transition-all duration-200 bg-accent text-[#06101F]";
    const TAB_INACTIVE = "flex-1 sm:flex-initial px-3.5 py-1.5 text-xs font-bold rounded-full transition-all duration-200 text-white/50 hover:text-white";

    const customTooltipOptions = {
        enabled: true,
        backgroundColor: "#131316",
        titleColor: "#F2F2F5",
        titleFont: { family: "Inter", weight: "bold", size: 11 },
        bodyColor: "#A9A9B2",
        bodyFont: { family: "Inter", size: 11 },
        borderColor: "rgba(255,255,255,0.1)",
        borderWidth: 1,
        padding: 10,
        displayColors: false,
        callbacks: {
            label: function (context) {
                let label = context.dataset.label || "";
                if (label) {
                    label += ": ";
                }
                if (context.parsed.y !== null) {
                    label += new Intl.NumberFormat("en-NG", { style: "currency", currency: "NGN" }).format(context.parsed.y);
                }
                return label;
            }
        }
    };

    function buildRevenueChart(canvasId, labels, values, datasetLabel) {
        const ctx = document.getElementById(canvasId).getContext("2d");
        const gradient = ctx.createLinearGradient(0, 0, 0, 240);
        gradient.addColorStop(0, "rgba(239, 68, 68, 0.65)");
        gradient.addColorStop(1, "rgba(239, 68, 68, 0.02)");

        return new Chart(ctx, {
            type: "bar",
            data: {
                labels: labels,
                datasets: [{
                    label: datasetLabel,
                    data: values,
                    backgroundColor: gradient,
                    borderColor: "rgba(239, 68, 68, 0.95)",
                    borderWidth: 1.5,
                    borderRadius: 6,
                    hoverBackgroundColor: "rgba(239, 68, 68, 1)",
                    hoverBorderColor: "#ffffff"
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: customTooltipOptions
                },
                scales: {
                    y: {
                        grid: { color: "rgba(255,255,255,0.06)" },
                        ticks: {
                            color: "#A9A9B2",
                            font: { family: "Inter", size: 9 },
                            callback: function (value) {
                                return "\u20a6" + new Intl.NumberFormat("en-US", { notation: "compact" }).format(value);
                            }
                        },
                        border: { dash: [4, 4] }
                    },
                    x: {
                        grid: { display: false },
                        ticks: {
                            color: "#A9A9B2",
                            font: { family: "Inter", size: 9 }
                        }
                    }
                }
            }
        });
    }

    function switchChart(type) {
        const btnMonthly = document.getElementById("btn-monthly");
        const btnAnnual = document.getElementById("btn-annual");
        const containerMonthly = document.getElementById("container-monthly");
        const containerAnnual = document.getElementById("container-annual");

        const showingMonthly = type === "monthly";

        btnMonthly.className = showingMonthly ? TAB_ACTIVE : TAB_INACTIVE;
        btnAnnual.className = showingMonthly ? TAB_INACTIVE : TAB_ACTIVE;

        containerMonthly.classList.toggle("hidden", !showingMonthly);
        containerAnnual.classList.toggle("hidden", showingMonthly);

        if (showingMonthly && monthlyChartInstance) {
            monthlyChartInstance.resize();
        } else if (!showingMonthly && annualChartInstance) {
            annualChartInstance.resize();
        }
    }

    window.switchChart = switchChart;

    document.addEventListener("DOMContentLoaded", function () {
        monthlyChartInstance = buildRevenueChart("monthlyChart", monthlyLabels, monthlyValues, "Monthly Revenue");
        annualChartInstance = buildRevenueChart("annualChart", annualLabels, annualValues, "Annual Revenue");
    });
})();