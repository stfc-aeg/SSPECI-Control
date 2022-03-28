
class SpectrometerAdapter extends AdapterEndpoint
{
    constructor(api_version=DEF_API_VERSION)
    {
        super("spectrometer", api_version);

        this.ele_main_spectrometer_status = document.getElementById("spec_connected");

        this.ele_btn_bin_full = document.getElementById("btnBinFull");
        this.ele_btn_bin_binned = document.getElementById("btnBin");
        this.ele_btn_bin_row = document.getElementById("btnBinRow");

        this.ele_input_bin_rows = document.getElementById("input-bin-rows");
        this.ele_input_bin_cols = document.getElementById("input-bin-cols");
        this.ele_input_bin_line = document.getElementById("input-bin-line");

        this.ele_input_cam_exposure = document.getElementById("input-camera-exposure");
        this.ele_input_cam_wavelength = document.getElementById("input-camera-wavelength");

        this.ele_input_frame_num = document.getElementById("input-frame-num");

        this.ele_btn_start_acq = document.getElementById("btn-start-acquisition");

        this.ele_spec_img = document.getElementById("spec_img_2");
        this.ele_spec_img_main = document.getElementById("spec_img");
        
        this.ele_btn_bin_full.addEventListener("click", (e) => this.bin_button_clicked(e));
        this.ele_btn_bin_binned.addEventListener("click", (e) => this.bin_button_clicked(e));
        this.ele_btn_bin_row.addEventListener("click", (e) => this.bin_button_clicked(e));

        this.ele_input_bin_rows.addEventListener("change", (e) => this.input_val_changed(e));
        this.ele_input_bin_cols.addEventListener("change", (e) => this.input_val_changed(e));
        this.ele_input_bin_line.addEventListener("change", (e) => this.input_val_changed(e));

        this.ele_input_cam_exposure.addEventListener("change", (e) => this.input_val_changed(e));
        this.ele_input_cam_wavelength.addEventListener("change", (e) => this.input_val_changed(e));

        this.ele_btn_start_acq.addEventListener("click", () => this.start_acquisition());


        this.get("")
        .then(response => {
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
        });
        this.img_refresh_loop();
    }

    start_acquisition(){
        var num_frames = this.ele_input_frame_num.value;
        this.put({"get_data": parseInt(num_frames)});
    }

    img_refresh_loop()
    {
        var img_start_time = new Date().getTime();
        this.ele_spec_img.setAttribute("src", this.ele_spec_img.getAttribute("data-src") + '?' + img_start_time);
        this.ele_spec_img_main.setAttribute("src", this.ele_spec_img.getAttribute("data-src") + '?' + img_start_time);
        // console.log("Image Updated");
        setTimeout(() => this.img_refresh_loop(), 1000);
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