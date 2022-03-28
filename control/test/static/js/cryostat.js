// import AdapterEndpoint from 'odin_control.js'

class CryostatAdapter extends AdapterEndpoint
{
    constructor(api_version=DEF_API_VERSION)
    {
        super("cryostat", api_version)

        this.atsm_temps = []
        this.stage1_temps = []
        this.stage2_temps = []
        this.platform_temps = []
        this.temp_timestamps = []
        this.temp_charts = []

        this.element_goal_label = document.getElementById('cryo_goal');
        this.element_state_label = document.getElementById('cryo_state');

        this.element_btn_cooldown = document.getElementById('btn-cooldown');
        this.element_btn_vent = document.getElementById('btn-vent');
        this.element_btn_vacuum = document.getElementById('btn-vacuum');
        this.element_btn_warmup = document.getElementById('btn-warmup');
        this.element_btn_abort = document.getElementById('btn-abort');

        this.power_schedule_enabled = false;
        this.element_btn_enable_pwr_schedule = document.getElementById("btn-toggle-power-schedule");
        this.element_input_heater_power = document.getElementById('input-heater-power');
        this.element_table_pwr_schedule = document.getElementById("power-schedule-table");

        this.element_btn_bakeout = document.getElementById("btn-toggle-bakeout");
        this.element_input_bakeout_temp = document.getElementById("input-bakeout-temp");
        this.element_input_bakeout_time = document.getElementById("input-bakeout-time");
        this.bakeout_enabled = false;

        this.element_btn_bakeout.addEventListener("change", () => this.toggle_bakeout());
        this.element_input_bakeout_temp.addEventListener("change", (e) => this.change_bakeout_temp(e));
        this.element_input_bakeout_time.addEventListener("change", (e) => this.change_bakeout_time(e));

        this.element_btn_enable_pwr_schedule.addEventListener("change", () => this.toggle_power_schedule());
        this.element_input_heater_power.addEventListener("change", (e) => this.change_power_limit(e));

        this.element_input_atsm_target = document.getElementById("input-atsm-target");
        this.element_input_platform_target = document.getElementById("input-platform-target");
        this.element_input_stage1_target = document.getElementById("input-stage1-target");
        this.element_input_stage2_target = document.getElementById("input-stage2-target");
        
        this.element_input_atsm_target.addEventListener("change", (e) => this.change_temp_target(e));
        this.element_input_platform_target.addEventListener("change", (e) => this.change_temp_target(e));

        this.element_pressure_label = document.getElementById("alert-vacuum-pressure");

        this.element_btn_abort.addEventListener("click", () => this.abort_clicked());
        this.element_btn_cooldown.addEventListener("click", () => this.cooldown_clicked());
        this.element_btn_vent.addEventListener("click", () => this.vent_clicked());
        this.element_btn_vacuum.addEventListener("click", () => this.vacuum_clicked());
        this.element_btn_warmup.addEventListener("click", () => this.warmup_clicked());

        this.icons = {
            "check": '<i class="bi bi-check-circle-fill"></i>',
            "exclaim": '<i class="bi bi-exclamation-octagon-fill"></i>',
            "spinner": '<div class="spinner-grow spinner-grow-sm" role="status"> <span class="visually-hidden">Loading</span></div>',
            "therm_snow": '<i class="bi bi-thermometer-snow"></i>',
            "therm_sun": '<i class="bi bi-thermometer-sun"></i>',
            "info": '<i class="bi bi-info-circle-fill"></i>'
        }

        this.element_schedule_dropdown = document.getElementById("power-schedule-dropdown");
        this.element_main_cryo_label = document.getElementById("main-cryo-connected");

        this.get()
        .then(response => {
            this.element_input_bakeout_temp.value = response.bakeout.temperature;
            this.element_input_bakeout_time.value = response.bakeout.time;
            this.bakeout_enabled = response.bakeout.enabled;
            this.element_btn_bakeout.checked = this.bakeout_enabled;

            var avail_schedules = response.atsm.power_schedules_avail;
            console.log(avail_schedules);
            avail_schedules.forEach(element => {
                var option = document.createElement("li");
                var option_link = document.createElement("a");
                option_link.href = "#";
                option_link.className = "dropdown-item";
                option_link.textContent = element;
                option_link.value = element;

                if(element == response.atsm.power_schedule_selected)
                {
                    option_link.classList.add("active");
                }

                option.appendChild(option_link);
                this.element_schedule_dropdown.appendChild(option);

                option_link.addEventListener("click", event => this.schedule_option_clicked(event));
            });
            this.construct_schedule_table();
            this.element_btn_enable_pwr_schedule.checked = response.atsm.power_schedule_enabled;

            this.element_input_atsm_target.value = response.atsm.target_temp;
            this.element_input_platform_target.value = response.platform.target_temp;
            this.element_input_stage1_target.value = response.stage1.target_temp;
            this.element_input_stage2_target.value = response.stage2.target_temp;
        });
    }

    change_temp_target(event)
    {

        var path = ""
        if(event.target == this.element_input_atsm_target)
        {
            path = "atsm";
        }
        else
        {
            path = "platform";
        }
        console.log(path + " target temp: " + event.target.value);
        this.put({"target_temp":parseFloat(event.target.value)}, path);
    }

    construct_schedule_table()
    {
        var table_body = this.element_table_pwr_schedule.getElementsByTagName('tbody')[1];
        table_body.innerHTML = ""; // clear the table body to be replaced
        this.get("atsm/power_schedule")
        .then(response => {
            console.log(response);
            for (var key in response.power_schedule)
            {
                var row = document.createElement("tr");
                var temp_cell = document.createElement("td");
                var power_cell = document.createElement("td");

                temp_cell.textContent = key;
                power_cell.textContent = response.power_schedule[key];

                row.appendChild(temp_cell);
                row.appendChild(power_cell);

                table_body.appendChild(row);
            }
        });
    }

    schedule_option_clicked(event)
    {
        console.log("Schedule Option Clicked: " + event.target.value);
        
        this.put({"power_schedule_selected": event.target.value}, "atsm")
        .then(() => {
            var dropdown_elements = this.element_schedule_dropdown.children;
            for(var i=0; i<dropdown_elements.length; i++) {
                dropdown_elements[i].firstElementChild.classList.remove('active');
            };
            event.target.classList.add("active");

            this.construct_schedule_table();
        });
    }

    change_bakeout_temp(event)
    {
        console.log("Changing Bakeout Temp to " + event.target.value);
        this.put({"temperature": parseFloat(event.target.value)}, "bakeout");
    }

    change_bakeout_time(event)
    {
        console.log("Changing Bakeout Time to " + event.target.value);
        this.put({"time": parseInt(event.target.value)}, "bakeout");
    }

    toggle_bakeout()
    {
        this.bakeout_enabled = !this.bakeout_enabled;
        this.put({"enabled": this.bakeout_enabled}, "bakeout");
        // if(this.bakeout_enabled == true)
        // {
        //     this.element_btn_bakeout.innerHTML = "Bakeout Enabled";
        // }else
        // {
        //     this.element_btn_bakeout.innerHTML = "Bakeout Disabled";
        // }

    }

    change_power_limit(event)
    {
        console.log("Setting Power Limit to " + event.target.value);
        this.put({"power_limit": parseFloat(event.target.value)}, "atsm")
            .then(() => {
                console.log("Changed Power limit");

            })
            .catch(error => {
                console.log(error.message);
            });
    }

    toggle_power_schedule()
    {
        console.log("Power Button Clicked");
        this.power_schedule_enabled = !this.power_schedule_enabled;
        this.put({"power_schedule_enabled": this.power_schedule_enabled}, "atsm");
    }

    cooldown_clicked()
    {
        console.log("cooldown Button Clicked");
        this.put({"begin_cooldown": true});
    }

    vent_clicked()
    {
        console.log("vent Button Clicked");
        this.put({"vent": true});
    }

    vacuum_clicked()
    {
        console.log("vacuum Button Clicked");
        this.put({"pull_vacuum": true});
    }

    warmup_clicked()
    {
        console.log("warmup Button Clicked");
        this.put({"warmup": true});
    }

    abort_clicked()
    {
        console.log("Abort Button Clicked");
        this.put({"abort": true});
    }

    build_chart(chart_element)
    {
        console.log("Creating Chart");
        var chart_temps = new Chart(chart_element,
            {
                type: 'line',
                // yAxisID: 'Temperature (K)',
                data: {
                    labels: this.temp_timestamps,
                    datasets: [{
                        label: "ATSM",
                        data: this.atsm_temps,
                        borderColor:['rgba(255, 0, 0, 1)'],
                        backgroundColor:['rgba(255, 0, 0, 0.1)'],
                        spanGaps: false,
                        pointStyle: "circle",
                        pointRadius: 10,
                        pointHoverRadius: 15
                    },
                    {
                        label: "Platform",
                        data: this.platform_temps,
                        borderColor:['rgba(0, 0, 255, 1)'],
                        backgroundColor: ['rgba(0, 0, 255, 0.1)'],
                        spanGaps: false,
                        pointStyle: "rectRot",
                        pointRadius: 10,
                        pointHoverRadius: 15
                    }
                    // {
                    //     label: "Stage 1",
                    //     data: this.stage1_temps,
                    //     borderColor:["rgba(0,255,0,1)"],
                    //     backgroundColor:['rgba(0, 255, 0, 0.1)'],
                    //     pointStyle: "crossRot",
                    //     pointRadius: 10,
                    //     pointHoverRadius: 15
                    // },
                    // {
                    //     label: "Stage 2",
                    //     data: this.stage2_temps,
                    //     borderColor:["rgba(0,0,255,1)"],
                    //     backgroundColor:['rgba(0, 0, 255, 0.1)'],
                    //     pointStyle: "rectRot",
                    //     pointRadius: 10,
                    //     pointHoverRadius: 15
                    // }
                    ]
                },
                options: {
                    responsive: true,
                    interaction: {
                        intersect: false,
                        mode: "index",
                    },
                    // animation: true,
                    scales: {
                        yAxes: [{
                            title: {
                                display: true,
                                text: "Temperature (K)"
                            },
                            ticks: {
                                // min: 0,
                                // max: 300,
                                stepSize: 2
                            }
                        }],
                        x: {
                            title: {
                                display: true,
                                text: "Time"
                            },
                            distribution: 'linear',
                            ticks: {
                                source: "data"
                            }
                        },   
                    },
                    plugins: {
                        legend: {
                            labels: {
                                usePointStyle: true,
                            },
                        }
                    }
                }
            })
        this.temp_charts.push(chart_temps);
    }

    update_temperatures(atsm_temp, stage1_temp, stage2_temp, platform_temp)
    {
        var max_length = 20;

        // console.log(response);
        // var atsm_temp = response.atsm.temperature.toFixed(5);
        // var stage1_temp = response.stage1.temperature.toFixed(5);
        // var stage2_temp = response.stage2.temperature.toFixed(5);
        
        this.atsm_temps.push(atsm_temp);
        if(this.atsm_temps.length > max_length) this.atsm_temps.shift();
        this.stage1_temps.push(stage1_temp);
        if(this.stage1_temps.length > max_length) this.stage1_temps.shift();
        this.stage2_temps.push(stage2_temp);
        if(this.stage2_temps.length > max_length) this.stage2_temps.shift();
        this.platform_temps.push(platform_temp);
        if(this.platform_temps.length > max_length) this.platform_temps.shift();

        var time = new Date();
        this.temp_timestamps.push(time.toLocaleTimeString("en-UK"));
        if(this.temp_timestamps.length > max_length) this.temp_timestamps.shift();

        for(var i=0; i<this.temp_charts.length; i++)
        {
            this.temp_charts[i].update();
        }
    }

    removeClassByPrefix(node, prefix) {
        var regx = new RegExp('\\b' + prefix + '[^ ]*[ ]?\\b', 'g');
        node.className = node.className.replace(regx, '');
        return node;
    }

    update_status(system_goal_string)
    {
        var goal = system_goal_string.split(":")[0].trim();
        var state = system_goal_string.split(":")[1].trim();

        this.removeClassByPrefix(this.element_goal_label, 'alert-');
        this.removeClassByPrefix(this.element_state_label, 'alert-');
        this.removeClassByPrefix(this.element_main_cryo_label, 'alert-');
        switch(goal){
            case "None":
                this.element_goal_label.innerHTML = this.icons["check"] + " Goal: None";
                this.element_goal_label.classList.add("alert-success");

                break;
            case "PullVacuum":
                this.element_goal_label.innerHTML = this.icons["info"] + " Goal: Pull Vacuum";
                this.element_goal_label.classList.add("alert-warning");
                break;
            case "Vent":
                this.element_goal_label.innerHTML = this.icons["info"] + " Goal: Venting";
                this.element_goal_label.classList.add("alert-warning");
                break;
            case "Cooldown":
                this.element_goal_label.innerHTML = this.icons["therm_snow"] + " Goal: Cooldown";
                this.element_goal_label.classList.add("alert-warning");
                break;
            case "Warmup":
                this.element_goal_label.innerHTML = this.icons["therm_sun"] + " Goal: Warmup";
                this.element_goal_label.classList.add("alert-warning");
                break;
            case "UNKNOWN":
            default:
                this.element_goal_label.innerHTML = this.icons["exclaim"] + " Goal: Unknown";
                this.element_goal_label.classList.add("alert-danger");
                break;
        }

        this.element_main_cryo_label.innerHTML = this.element_goal_label.innerHTML.replace("Goal", "Cryo Status");
        this.element_main_cryo_label.classList = this.element_goal_label.classList;

        switch(state){
            case "Idle":
            case "Ready":
                this.element_state_label.innerHTML = this.icons["check"] + " State: " + state;
                this.element_state_label.classList.add("alert-success");
                break;
            case "Configuring":
                this.element_state_label.innerHTML = this.icons["info"] + " State: Configuring";
                this.element_state_label.classList.add("alert-warning");
                break;
            case "WaitingForVacuumSystem":
                this.element_state_label.innerHTML = this.icons["info"] + " State: Waiting For Vacuum System";
                this.element_state_label.classList.add("alert-warning");
                break;
            case "CleaningVacuumLines":
                this.element_state_label.innerHTML = this.icons["info"] + " State: Cleaning Vacuum Lines";
                this.element_state_label.classList.add("alert-warning");
                break;
            case "CheckingForLeaks":
                this.element_state_label.innerHTML = this.icons["info"] + " State: Checking For Leaks";
                this.element_state_label.classList.add("alert-warning");
                break;
            case "BakeoutPreheating":
                this.element_state_label.innerHTML = this.icons["therm_sun"] + " State: Bakeout Preheating";
                this.element_state_label.classList.add("alert-warning");
                break;
            case "BakingOut":
                this.element_state_label.innerHTML = this.icons["therm_sun"] + " State: Baking Out";
                this.element_state_label.classList.add("alert-warning");
                break;
            case "Purging":
                this.element_state_label.innerHTML = this.icons["info"] + " State: Purging";
                this.element_state_label.classList.add("alert-warning");
                break;
            case "PullingVacuum":
                this.element_state_label.innerHTML = this.icons["info"] + " State: Pulling Vacuum";
                this.element_state_label.classList.add("alert-warning");
                break;
            case "CoolingDown":
                this.element_state_label.innerHTML = this.icons["therm_snow"] + " State: Cooling Down";
                this.element_state_label.classList.add("alert-warning");
                break;
            case "AcquiringTarget":
                this.element_state_label.innerHTML = this.icons["info"] + " State: Acquiring Target";
                this.element_state_label.classList.add("alert-warning");
                break;
            case "StableAtTarget":
                this.element_state_label.innerHTML = this.icons["check"] + " State: Stable At Target";
                this.element_state_label.classList.add("alert-success");
                break;
            case "WarmingUp":
                this.element_state_label.innerHTML = this.icons["therm_sun"] + " State: Warming Up";
                this.element_state_label.classList.add("alert-warning");
                break;
            case "Venting":
                this.element_state_label.innerHTML = this.icons["info"] + " State: Venting";
                this.element_state_label.classList.add("alert-warning");
                break;
            case "Invalid":
            case "UNKNOWN":
            default:
                this.element_state_label.innerHTML = this.icons["exclaim"] + " State: " + state;
                this.element_state_label.classList.add("alert-danger");
                break;
        }
        // this.element_goal_label.innerHTML = "Goal: " + goal;
        // this.element_state_label.innerHTML = "State: " + state;
    }

    update_buttons(can_cool, can_vent, can_vacuum, can_warmup, can_abort)
    {   
        this.element_btn_cooldown.disabled = !can_cool;
        this.element_btn_vent.disabled = !can_vent;
        this.element_btn_vacuum.disabled = !can_vacuum;
        this.element_btn_warmup.disabled = !can_warmup;
        this.element_btn_abort.disabled = !can_abort;
    }

    update_pwr_schedule(power_limit)
    {
        if(this.power_schedule_enabled == true)
        {
            // console.log("Schedule Enabled");
            // this.element_btn_enable_pwr_schedule.innerHTML = "Power Schedule Enabled";
            
            this.element_input_heater_power.readOnly = true;
            this.element_input_heater_power.value = power_limit;
        }
        else
        {
            // console.log("Schedule Disabled");
            // this.element_btn_enable_pwr_schedule.innerHTML = "Power Schedule Disabled";
            // this.element_btn_enable_pwr_schedule.checked = false;
            this.element_input_heater_power.readOnly = false;
        }
    }


    poll_loop()
    {
        this.get('').then(response => {
            var atsm_temp = response.atsm.temperature.toFixed(5);
            var stage1_temp = response.stage1.temperature.toFixed(5);
            var stage2_temp = response.stage2.temperature.toFixed(5);
            var platform_temp = response.platform.temperature.toFixed(5);

            this.update_temperatures(atsm_temp, stage1_temp, stage2_temp, platform_temp);

            var system_goal_string = response.system_goal;
            this.update_status(system_goal_string);

            var can_cool = response.capabilities.can_cooldown;
            var can_vent = response.capabilities.can_vent;
            var can_vacuum = response.capabilities.can_pull_vacuum;
            var can_warmup = response.capabilities.can_warmup;
            var can_abort = response.capabilities.can_abort;
            this.update_buttons(can_cool, can_vent, can_vacuum, can_warmup, can_abort);

            this.power_schedule_enabled = response.atsm.power_schedule_enabled;
            var power_limit = response.atsm.power_limit;
            this.update_pwr_schedule(power_limit);

            // this.element_input_atsm_target.value = response.atsm.target_temp;
            // this.element_input_platform_target.value = response.platform.target_temp;
            this.element_input_stage1_target.value = response.stage1.target_temp;
            this.element_input_stage2_target.value = response.stage2.target_temp;

            var pressure = response.vacuum.toFixed(8);
            if(pressure < 50) //TODO: arbitary value, ask Sion what might be a valid pressure for this
            {
                this.element_pressure_label.innerHTML = this.icons["check"] + " " + pressure + " Pascals";
                this.element_pressure_label.classList.remove("alert-danger");
                this.element_pressure_label.classList.add("alert-success");
            }
            else
            {
                this.element_pressure_label.innerHTML = this.icons["exclaim"] + " " + pressure + " Pascals";
                this.element_pressure_label.classList.remove("alert-success");
                this.element_pressure_label.classList.add("alert-danger");
            }
        })

        setTimeout(() => this.poll_loop(), 1000);
    }

}

$( document ).ready(function() {
    cryo_adapter = new CryostatAdapter()
    chart_elements = document.getElementsByClassName("chart-temperature");
    console.log("Chart Elements: " + chart_elements.length)
    for(var i=0; i<chart_elements.length; i++){
        cryo_adapter.build_chart(chart_elements[i].getContext("2d"));
    }

    cryo_adapter.poll_loop();
});