api_version = '0.1';
adapter_name = 'zerorpc';

$(document).ready(function() {

    init();

});


function init() {

    img_elem = $('#data_img')
    setInterval(updateImage, 500);
    $("[name='btnradio_bin']").on('click', (function(e)
    {
        console.log("Radio Changed: " + e.type);
        console.log($(this).val())
        $.ajax({type: "PUT",
                url: '/api/' + api_version + '/' + adapter_name + "/binning",
                contentType: "application/json",
                data: JSON.stringify({"binning_mode": $(this).val()}),
            success: function(data) {
                console.log("Binning Mode Changed");
            }

        });
    }));

    input_bin_rows = document.getElementById("input-bin-rows");
    input_bin_rows.onchange = function()
    {
        console.log("Bin Rows Changed: " + input_bin_rows.value);
        $.ajax({type: "PUT",
                url: '/api/' + api_version + '/' + adapter_name + "/binning",
                contentType: "application/json",
                data: JSON.stringify({"bin_height": parseInt(input_bin_rows.value)})
        });
    }

    input_bin_cols = document.getElementById("input-bin-cols");
    input_bin_cols.onchange = function()
    {
        console.log("Bin Columns Changed: " + input_bin_cols.value);
        $.ajax({type: "PUT",
                url: '/api/' + api_version + '/' + adapter_name + "/binning",
                contentType: "application/json",
                data: JSON.stringify({"bin_width": parseInt(input_bin_cols.value)})
        });
    }
}

function acquire() {
    console.log("Ooo button pressed");
    num_frames = document.getElementById("input-num-frames");
    $.ajax({type: "PUT",
            url:'/api/' + api_version + '/' + adapter_name,
            contentType: "application/json",
            data: JSON.stringify({'get_data': parseInt(num_frames.value)}),
        success: function(data) {
            console.log("Acquisition complete");
            // updateImage();
        }
    });
}

function updateImage() {
    img_start_time = new Date().getTime();
    img_elem.attr("src", img_elem.attr("data-src") + '?' + img_start_time);
    console.log("Image Updated");
}