
class SpectrometerAdapter extends AdapterEndpoint
{
    constructor(api_version=DEF_API_VERSION)
    {
        super("spectrometer", api_version);

        this.ele_main_spectrometer_status = document.getElementById("main-spec-connected");

        this.ele_btn_bin_full = document.getElementById("btnBinFull");
        this.ele_btn_bin_binned = document.getElementById("btnBin");
        this.ele_btn_bin_row = document.getElementById("btnBinRow");

        this.ele_input_bin_rows = document.getElementById("input-bin-rows");
        this.ele_input_bin_cols = document.getElementById("input-bin-cols");
        this.ele_input_bin_line = document.getElementById("input-bin-line");

        this.ele_input_cam_exposure = document.getElementById("input-camera-exposure");
        this.ele_input_cam_wavelength = document.getElementById("input-camera-wavelength");

        this.ele_input_frame_num = document.getElementById("input-frame-num");

        this.ele_btn_start_lf = document.getElementById("btn-start-lightfield");
        this.ele_btn_start_acq = document.getElementById("btn-start-acquisition");

        this.ele_spec_img = document.getElementById("spec_img_2");
        this.ele_spec_img_main = document.getElementById("spec_img");

        this.ele_load_experi_drop_btn = document.getElementById("btn-select-experiement-file");
        this.ele_experi_drop_list = document.getElementById("experiment-file-dropdown");

        this.ele_save_experi_input = document.getElementById("input-experiment-file-name");
        this.ele_save_experi_btn = document.getElementById("btn-save-experiment-file");

        
        this.ele_btn_bin_full.addEventListener("click", (e) => this.bin_button_clicked(e));
        this.ele_btn_bin_binned.addEventListener("click", (e) => this.bin_button_clicked(e));
        this.ele_btn_bin_row.addEventListener("click", (e) => this.bin_button_clicked(e));

        this.ele_input_bin_rows.addEventListener("change", (e) => this.input_val_changed(e));
        this.ele_input_bin_cols.addEventListener("change", (e) => this.input_val_changed(e));
        this.ele_input_bin_line.addEventListener("change", (e) => this.input_val_changed(e));

        this.ele_input_cam_exposure.addEventListener("change", (e) => this.input_val_changed(e));
        this.ele_input_cam_wavelength.addEventListener("change", (e) => this.input_val_changed(e));

        this.ele_btn_start_lf.addEventListener("click", () => this.start_lightfield());
        this.ele_btn_start_acq.addEventListener("click", () => this.start_acquisition());

        this.ele_save_experi_btn.addEventListener("click", () => this.save_experiment_clicked());

        this.avail_experiment_files = [];

        this.get("")
        .then(response => {
            this.set_experiment_values(response)

            this.avail_experiment_files = response.experiments.list_experiments;
            this.populate_experiment_dropdown(this.avail_experiment_files);
        });
        this.img_refresh_loop();
    }

    set_experiment_values(response)
    {
        var bin_type = response.binning.binning_mode;
            switch(bin_type){
                case "FullSensor": this.ele_btn_bin_full.checked = true; break;
                case "BinnedSensor": this.ele_btn_bin_binned.checked = true; break;
                case "LineSensor": this.ele_btn_bin_row.checked = true; break;
            }

            this.ele_input_bin_rows.value = response.binning.bin_height;
            this.ele_input_bin_cols.value = response.binning.bin_width;
            this.ele_input_bin_line.value = response.binning.row_bin_centre;

            this.ele_input_cam_exposure.value = response.acquisition.exposure;
            this.ele_input_cam_wavelength.value = response.acquisition.centre_wavelength;
    }

    start_acquisition(){
        var num_frames = this.ele_input_frame_num.value;
        this.put({"get_data": parseInt(num_frames)});
    }

    start_lightfield(){
        this.put({"start_lightfield": true})
        .then(response => {

        });
    }

    img_refresh_loop()
    {
        var img_start_time = new Date().getTime();
        this.ele_spec_img.setAttribute("src", this.ele_spec_img.getAttribute("data-src") + '?' + img_start_time);
        this.ele_spec_img_main.setAttribute("src", this.ele_spec_img.getAttribute("data-src") + '?' + img_start_time);
        // console.log("Image Updated");
        setTimeout(() => this.img_refresh_loop(), 1000);
    }

    populate_experiment_dropdown(experiment_list)
    {
        this.ele_experi_drop_list.innerHTML = "";  // clear the dropdown to avoid duplicates
        experiment_list.forEach(element => {

            var option = document.createElement("li");
            var option_link = document.createElement("a");
            option_link.href = "#";
            option_link.className = "dropdown-item";
            option_link.textContent = element;
            option_link.value = element;

            option.appendChild(option_link);
            this.ele_experi_drop_list.appendChild(option);

            option_link.addEventListener("click", event => this.load_experiment_clicked(event));
        });
    }

    load_experiment_clicked(event)
    {
        console.log("Load Experiment clicked: " + event.target.value);
        this.put({"load_experiment": event.target.value}, "experiments");
        this.ele_save_experi_input.value = event.target.value;
        this.get("")
        .then(response => this.set_experiment_values(response));

    }

    save_experiment_clicked()
    {
        console.log("Save Experiment Clicked");
        var value = this.ele_save_experi_input.value;
        if(this.avail_experiment_files.includes(value))
        {
            if(!confirm(value + " already exists. Overwrite?"))
            {
                return;
            }
        }

        this.put({"save_experiment": value}, "experiments")
        .then(response => {
            console.log(response);
            this.avail_experiment_files = response.experiments.list_experiments;
            this.populate_experiment_dropdown(this.avail_experiment_files);
        });

    }

    bin_button_clicked(event)
    {
        console.log(event.target.value);

        this.put({"binning_mode": event.target.value}, "binning");
    }

    input_val_changed(event)
    {
        console.log(event.target.id + ":" + event.target.value);
        if(event.target == this.ele_input_bin_rows)
        {
            this.put({"bin_height": parseInt(event.target.value)}, "binning");
        } else if(event.target == this.ele_input_bin_cols)
        {
            this.put({"bin_width": parseInt(event.target.value)}, "binning");
        } else if(event.target == this.ele_input_bin_line)
        {
            this.put({"row_bin_centre": parseInt(event.target.value)}, "binning");
        } else if(event.target == this.ele_input_cam_exposure)
        {
            this.put({"exposure": parseInt(event.target.value)}, "acquisition");
        } else if(event.target == this.ele_input_cam_wavelength)
        {
            this.put({"centre_wavelength": parseInt(event.target.value)}, "acquisition");
        }
    }
}


$( document ).ready(function() {
    spec_adapter = new SpectrometerAdapter();
});