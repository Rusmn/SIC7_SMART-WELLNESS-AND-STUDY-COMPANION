function pad(n) {
    return n < 10 ? "0" + n : n;
}

function asClock(sec) {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${pad(m)}:${pad(s)}`;
}

document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.onclick = () => {
        document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById(btn.dataset.tab).classList.add("active");
    };
});

async function calcPlan() {
    const duration = Math.max(1, parseInt(document.getElementById("durationInput").value || "0", 10));
    const r = await fetch("/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duration_min: duration }),
    });
    const p = await r.json();
    
    document.getElementById("plan-interval").textContent = p.break_interval_min;
    document.getElementById("plan-count").textContent = p.break_count;
    document.getElementById("plan-length").textContent = p.break_length_min;
    document.getElementById("plan-water-count").textContent = p.water_milestones.length;
    document.getElementById("plan-water-per").textContent = p.water_ml;
    document.getElementById("plan-water-total").textContent = p.water_total_ml;
    
    renderWaterList(p.water_milestones, p.water_ml);
    return p;
}

document.getElementById("btn-calc").onclick = calcPlan;

document.getElementById("btn-start").onclick = async () => {
    const duration = Math.max(1, parseInt(document.getElementById("durationInput").value || "0", 10));
    await fetch("/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duration_min: duration }),
    });
    await calcPlan();
};

document.getElementById("btn-stop").onclick = async () => {
    await fetch("/stop", { method: "POST" });
};

document.getElementById("btn-reset").onclick = async () => {
    await fetch("/reset", { method: "POST" });
    renderWaterList([], 0);
};

function renderWaterList(milestones, per_ml) {
    const host = document.getElementById("water-list");
    if (!milestones || milestones.length === 0) {
        host.innerHTML = '<div class="hint">Tidak ada milestone minum. Hitung plan lalu mulai.</div>';
        return;
    }
    const items = milestones.map((sec, idx) => {
        const t = asClock(sec);
        return `
        <div class="water-item" data-id="${idx}">
            <div class="water-left">
                <div class="water-title">Milestone ${idx + 1}</div>
                <div class="water-time">At ${t}</div>
            </div>
            <div class="water-right">
                <div class="water-ml">${per_ml} ml</div>
                <label class="water-check">
                    <input type="checkbox" data-check="${idx}"> Done
                </label>
            </div>
        </div>`;
    }).join("");
    
    host.innerHTML = items;
    
    host.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
        cb.onchange = async (e) => {
            const id = parseInt(e.target.getAttribute("data-check"), 10);
            if (e.target.checked) {
                await fetch("/water_ack", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ milestone_id: id }),
                });
            }
        };
    });
}

function updateWaterActive(map) {
    const host = document.getElementById("water-list");
    host.querySelectorAll(".water-item").forEach((el) => {
        const id = parseInt(el.getAttribute("data-id"), 10);
        const active = !!map[id];
        el.classList.toggle("active", active);
    });
}

async function refreshState() {
    try {
        const r = await fetch("/status"); 
        const d = await r.json();
        
        const s = d.scheduler;
        document.getElementById("phase-label").textContent = s.phase.toUpperCase();
        document.getElementById("phase-time").textContent = asClock(s.phase_remaining_sec);
        document.getElementById("total-time").textContent = asClock(s.total_remaining_sec);
        
        if(s.water_active) updateWaterActive(s.water_active);

        const sensor = d.sensor;
        const lightText = sensor.light === "0" ? "Gelap" : "Terang";
        
        document.getElementById("nav-temp").textContent = sensor.temperature;
        document.getElementById("nav-hum").textContent = sensor.humidity;
        document.getElementById("nav-light").textContent = lightText;
        document.getElementById("nav-status").textContent = d.status;

        document.getElementById("mon-temp").textContent = sensor.temperature;
        document.getElementById("mon-hum").textContent = sensor.humidity;
        document.getElementById("mon-light").textContent = lightText;

        if(d.emotion) {
            document.getElementById("mon-emotion").textContent = d.emotion.label;
            document.getElementById("mon-emo-score").textContent = Math.round(d.emotion.score * 100);
        }

        const summaryCard = document.getElementById("mon-summary-card");
        const summaryText = document.getElementById("mon-summary-text");
        const navbar = document.querySelector(".navbar");
        const env = d.env_prediction || { label: "Model not ready", confidence: 0 };
        summaryText.textContent = `${env.label} (${Math.round(env.confidence * 100)}%)`;

        if (d.alert_level === "good") {
            navbar.style.background = "rgba(0,128,0,0.4)";
            summaryCard.className = "monitor-summary-card good";
        } else if (d.alert_level === "bad") {
            navbar.style.background = "rgba(200,0,0,0.6)";
            summaryCard.className = "monitor-summary-card bad";
        } else {
            navbar.style.background = "rgba(30, 75, 138, 0.9)";
            summaryCard.className = "monitor-summary-card unknown";
        }

    } catch (e) {
        console.log(e);
    }
}

setInterval(refreshState, 1000);
