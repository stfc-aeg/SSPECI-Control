class AcquisitionAdapter extends AdapterEndpoint
{
    constructor(api_version=DEF_API_VERSION)
    {
        super("acquisition", api_version);

        this.ele_number_frames = document.getElementById("input-frame-num");
        this.ele_file_name = document.getElementById("input-hdf-file-name");
        this.ele_acq_status = document.getElementById("system_status");
        this.btn_acq_start = document.getElementById("btn-start-acq");
        this.btn_acq_stop = document.getElementById("btn-stop-acq");
        this.ele_acq_progress = document.getElementById("acq-progress");

        this.btn_modal_acq_start = document.getElementById("btn-modal-start-acq");
        this.btn_modal_acq_stop = document.getElementById("btn-modal-stop-acq");

        this.btn_temperature_list_dropdown = document.getElementById("btn-select-temperature-list");
        this.ele_temperature_dropdown = document.getElementById("temperature-list-dropdown");
        this.tbl_temperature_list = document.getElementById("temperature-list-table");
        
        
        this.disable_when_running = [

        ];


        this.get("")
        .then(response => {
            this.set_running_label(response.state, response.filename);
            this.set_filename_textbox(response.filename);
            var avail_temp_lists = response.photo_mode_temps_avail;

            avail_temp_lists.forEach(element => {
                var option = document.createElement("li");
                var option_link = document.createElement("a");
                option_link.href = "#";
                option_link.className = "dropdown-item";
                option_link.textContent = element;
                option_link.value = element;

                if(element == response.temp_list_selected)
                {
                    option_link.classList.add("active");
                }

                option.appendChild(option_link);
                this.ele_temperature_dropdown.appendChild(option);

                option_link.addEventListener("click", event => this.temperature_option_clicked(event));
            });

            this.construct_temperature_table();
        });

        this.btn_acq_start.addEventListener("click", (e) => this.start_acquisition(e));
        this.btn_acq_stop.addEventListener("click", (e) => this.stop_acquisition(e));
    }

    set_running_label(is_running, file_name)
    {
        console.log("state: " + is_running); 
        this.removeClassByPrefix(this.ele_acq_status, "alert-");
        switch(is_running)
        {
            case "READY":
                this.ele_acq_status.innerHTML = "Acquisition NOT Running";
                this.ele_acq_status.classList.add("alert-success");
                
                this.btn_modal_acq_start.disabled = false;
                this.btn_modal_acq_stop.disabled = true;
                break;
            case "WAIT_FRAME":
            case "FRAME_READY":
            case "TEMP_READY":
            case "WAIT_STABLE_RESET":
                this.ele_acq_status.innerHTML = "Acquisition Running";
                this.ele_acq_status.classList.add("alert-warning");

                this.btn_modal_acq_start.disabled = true;
                this.btn_modal_acq_stop.disabled = false;
                break;
            case "COMPLETE":
                this.ele_acq_status.innerHTML = "Acqusition Finished";
                this.ele_acq_status.classList.add("alert-success");
                this.btn_modal_acq_start.disabled = false;
                this.btn_modal_acq_stop.disabled = true;
                break;
            case "WAIT_TEMP":
                this.ele_acq_status.innerHTML = "Acquisition Waiting for Temperature";
                this.ele_acq_status.classList.add("alert-warning");
                this.btn_modal_acq_start.disabled = true;
                this.btn_modal_acq_stop.disabled = false;
                break;
            case "error":
            default:
                this.ele_acq_status.innerHTML = "Acqusition Error: Filename Already Exists"
                this.ele_acq_status.classList.add("alert-danger");
                this.btn_modal_acq_start.disabled = false;
                this.btn_modal_acq_stop.disabled = true;
        }
        this.ele_acq_status.innerText = this.ele_acq_status.innerHTML.concat(`: ${file_name}`)

        this.is_running = is_running;
    }
    set_progress(current_val, max_val)
    {
        this.ele_acq_progress.setAttribute("aria-valuenow", current_val);
        this.ele_acq_progress.setAttribute("aria-valuemax", max_val);
        if(max_val != 0)
        {
            var width_val = (current_val / max_val) * 100;
            this.ele_acq_progress.setAttribute("style", `width: ${width_val}%`);
            this.ele_acq_progress.innerHTML = `${current_val}/${max_val}`;
            this.ele_acq_status.innerHTML += `: ${current_val}/${max_val}`;
        }else{
            this.ele_acq_progress.setAttribute("style", "width: 0%");
            this.ele_acq_progress.innerHTML = "No Frames Requested";
        }
    }
    set_filename_textbox(filename)
    {
        this.ele_file_name.value = filename
    }

    start_acquisition(event)
    {
        var num_frames = this.ele_number_frames.value;
        var file_name = this.ele_file_name.value;

        this.put({"filename": file_name});
        this.put({"start_acquisition": parseInt(num_frames)});
    }

    stop_acquisition(event)
    {
        this.put({"stop_acquisition": true});

    }
    poll_loop()
    {
        this.get("").then(response => {
            this.set_running_label(response.state, response.filename);
            this.set_progress(response.current_frames, response.max_frames);
        });

        setTimeout(() => this.poll_loop(), 1000);
    }

    construct_temperature_table()
    {
        console.log("Constructing Temperature Table");
        var table_body = this.tbl_temperature_list.getElementsByTagName('tbody')[0];
        console.log(this.tbl_temperature_list);
        console.log(table_body);
        table_body.innerHTML = ""; // clear the table body to be replaced
        this.get("temp_list")
        .then(response => {
            response.temp_list.forEach(element => {
                var row = document.createElement("tr");
                var temp_cell = document.createElement("td");

                temp_cell.textContent = element;

                row.appendChild(temp_cell);

                table_body.appendChild(row);
            });
        });
    }

    temperature_option_clicked(event)
    {
        this.put({"temp_list_selected": event.target.value}, "")
        .then(() => {
            var dropdown_elements = this.ele_temperature_dropdown.children;
            for(var i=0; i<dropdown_elements.length; i++) {
                dropdown_elements[i].firstElementChild.classList.remove('active');
            };
            event.target.classList.add("active");

            this.construct_temperature_table();
        });
    }
}

$( document ).ready(function() {
    acq_adapter = new AcquisitionAdapter();

    acq_adapter.poll_loop();
});