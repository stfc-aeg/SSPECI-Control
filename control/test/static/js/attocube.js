
class AxisElements
{
    constructor(axis_num)
    {
        var axis_label = "axis" + axis_num
        this.ele_pos = document.getElementById("badge-" + axis_label + "-pos");
        this.ele_target_value = document.getElementById("badge-" + axis_label + "-target");
        this.ele_target_reached = document.getElementById("badge-" + axis_label + "-target-reached");
        this.ele_is_moving = document.getElementById(axis_label + "-is-moving");

        this.ele_travel_end_front = document.getElementById("badge-" + axis_label + "-EoTF");
        this.ele_travel_end_back = document.getElementById("badge-" + axis_label + "-EoTB");

        this.ele_axis_name = document.getElementById(axis_label + "-axis-name");
        this.ele_amplitude = document.getElementById(axis_label + "-amplitude");
        this.ele_frequency = document.getElementById(axis_label + "-frequency");
        this.ele_target_range = document.getElementById(axis_label + "-target-range");

        this.ele_save_position = document.getElementById("input-" + axis_label + "-save-position");
        this.ele_save_range    = document.getElementById("input-" + axis_label + "-save-range");

        this.ele_toggle_move = document.getElementById("btn-toggle-move-" + axis_label);

        this.icons = {
            "check": '<i class="bi bi-check-circle-fill"></i>',
            "exclaim": '<i class="bi bi-exclamation-octagon-fill"></i>',
            "arrows": '<i class="bi bi-arrow-left-right"></i>'
        }
    }

    set_save_text_boxes(position, range)
    {
        this.ele_save_position.value = position;
        this.ele_save_range.value = range;
    }

    get_save_text_boxes()
    {
        return [parseFloat(this.ele_save_position.value),
                parseFloat(this.ele_save_range.value)]
    }

    removeClassByPrefix(node, prefix) {
        var regx = new RegExp('\\b' + prefix + '[^ ]*[ ]?\\b', 'g');
        node.className = node.className.replace(regx, '');
        return node;
    }

    update_values(value_dict)
    {
        this.ele_pos.innerHTML = "Position(mm): " + (parseFloat(value_dict.position)*1000).toFixed(6);
        this.ele_target_value.innerHTML = "Target: " + (parseFloat(value_dict.target_pos)*1000).toFixed(6);

        this.removeClassByPrefix(this.ele_target_reached, "bg-")
        if(value_dict.at_target)
        {
            this.ele_target_reached.innerHTML = "Target Reached";
            // this.ele_target_reached.classList.remove("bg-danger");
            this.ele_target_reached.classList.add("bg-success");
        }
        else
        {
            this.ele_target_reached.innerHTML = "Target Not Reached";
            // this.ele_target_reached.classList.remove("bg-success");
            this.ele_target_reached.classList.add("bg-danger");
        }

        this.removeClassByPrefix(this.ele_is_moving, "alert-");
        if(value_dict.moving)
        {
            this.ele_is_moving.innerHTML = this.icons.arrows + "Axis Is Moving";
            this.ele_is_moving.classList.add("alert-warning");
        }
        else
        {
            this.ele_is_moving.innerHTML = "Axis Stopped";
            this.ele_is_moving.classList.add("alert-info");
        }

        this.removeClassByPrefix(this.ele_travel_end_back, "bg-");
        this.removeClassByPrefix(this.ele_travel_end_front, "bg-");
        if(value_dict.end_of_travel.backward)
        {
            this.ele_travel_end_back.innerHTML = "Backward:" + this.icons.exclaim;
            this.ele_travel_end_back.classList.add("bg-danger");
        }
        else
        {
            this.ele_travel_end_back.innerHTML = "Backward:" + this.icons.check;
            this.ele_travel_end_back.classList.add("bg-success");
        }

        if(value_dict.end_of_travel.forward)
        {
            this.ele_travel_end_front.innerHTML = "Forward:" + this.icons.exclaim;
            this.ele_travel_end_front.classList.add("bg-danger");
        }
        else
        {
            this.ele_travel_end_front.innerHTML = "Forward:" + this.icons.check;
            this.ele_travel_end_front.classList.add("bg-success");
        }

        this.ele_axis_name.value = value_dict.axis_name;
        this.ele_amplitude.value = value_dict.amplitude;
        this.ele_frequency.value = value_dict.frequency;
        this.ele_target_range.value = value_dict.target_range;

    }
}


class AttocubeAdapter extends AdapterEndpoint
{
    constructor(api_version=DEF_API_VERSION)
    {
        super("attocube", api_version);

        this.axis_elements = [
            new AxisElements(0),
            new AxisElements(1),
            new AxisElements(2)
        ]

        this.ele_position_dropdown = document.getElementById("position-file-dropdown");
        this.ele_input_file_name = document.getElementById("input-position-file-name");
        this.ele_btn_save_file = document.getElementById("btn-save-position-file");
        this.ele_main_atto_label = document.getElementById("main-atto-connected");

        this.get("position_files")
        .then(response => {
            this.position_files = response.position_files;
            this.build_dropdown(this.position_files);
        });

        this.ele_btn_save_file.addEventListener("click", () => this.save_position());

        this.axis_elements.forEach(element => {
            element.ele_save_position.addEventListener("change", (event) => this.save_position_changed(event));
            element.ele_save_range.addEventListener("change", (event) => this.save_position_changed(event));
            element.ele_toggle_move.addEventListener("change", (event) => this.set_auto_move(event));
        });


        this.update_loop();
    }

    save_position_changed(event)
    {
        var regex = /axis[0-9]/;
        var axis_label = event.target.id.match(regex)[0];
        var axis_label = axis_label.replace("axis", "axis_")
        console.log(axis_label);

        if(event.target.id.includes("position"))
        {
            this.put({"target_pos": parseFloat(event.target.value)}, axis_label);
        }
        else
        {
            this.put({"target_range": parseFloat(event.target.value)}, axis_label);
        }

    }

    set_auto_move(event)
    {
        var regex = /axis[0-9]/;
        var axis_label = event.target.id.match(regex)[0];
        var axis_label = axis_label.replace("axis", "axis_")
        console.log(axis_label);

        console.log(event.target.checked);

        this.put({"auto_move": event.target.checked}, axis_label);
    }

    update_loop()
    {
        this.get('').then(response => {
            var axis0_info = response.axis_0;
            var axis1_info = response.axis_1;
            var axis2_info = response.axis_2;

            this.axis_elements[0].update_values(axis0_info);
            this.axis_elements[1].update_values(axis1_info);
            this.axis_elements[2].update_values(axis2_info);

            this.removeClassByPrefix(this.ele_main_atto_label, "alert-");
            if(response.device_connected)
            {
                this.ele_main_atto_label.innerHTML = '<i class="bi bi-check-circle-fill"></i>' + " Attocube Connected";
                this.ele_main_atto_label.classList.add("alert-success");
            }
            else
            {
                this.ele_main_atto_label.innerHTML = '<i class="bi bi-exclamation-octagon-fill"></i>' + " Attocube Disconnected";
                this.ele_main_atto_label.classList.add("alert-danger");
            }
            
        });
        setTimeout(() => this.update_loop(), 1000);
    }

    position_dropdown_clicked(event)
    {
        console.log("Position Dropdown Clicked: " + event.target.value);
        this.put({"load_position": event.target.value})
        .then(response => {

            this.axis_elements[0].set_save_text_boxes(response.axis_0.target_pos, response.axis_0.target_range);
            this.axis_elements[1].set_save_text_boxes(response.axis_1.target_pos, response.axis_1.target_range);
            this.axis_elements[2].set_save_text_boxes(response.axis_2.target_pos, response.axis_2.target_range);
        });

    }

    build_dropdown(file_list)
    {
        this.ele_position_dropdown.innerHTML = "";
        file_list.forEach(element => {
            var option = document.createElement("li");
                var option_link = document.createElement("a");
                option_link.href = "#";
                option_link.className = "dropdown-item";
                option_link.textContent = element.split(".").slice(0, -1).join('.');
                option_link.value = element;

                option.appendChild(option_link);
                this.ele_position_dropdown.appendChild(option);

                option_link.addEventListener("click", event => this.position_dropdown_clicked(event));
        });
    }

    save_position()
    {

        var value = this.ele_input_file_name.value;
        if(!value.endsWith(".json"))
        {
            value = value + ".json";
        }
        if(this.position_files.includes(value))
        {
            if(!confirm(value + " already exists. Overwrite?"))
            {
                return;
            }
        }

        this.put({"save_position": value})
        .then(response => {
            this.position_files = response.position_files;
            this.build_dropdown(this.position_files);
        })
    }
}

$( document ).ready(function() {
    attocube_adapter = new AttocubeAdapter();

});