import gp_align
import skimage
import skimage.feature
import skimage.io
import os
import numpy as np
import pandas as pd

CANNY_SIGMA = 1

def analyse_run(image_list, plate_type=1, parse_dates=True, orientation="bottom_left", plates=None, plate_names=None):
    """
    Analyse a list of images from the Growth Profiler.

    Parameters:
    plate_type: The type of plates used
    parse_dates: Whether to sort the images by time. The image_names must of format '%d%m%Y%H%M%S'
    orientation: The orientation of the plates in the machine. The corner where A1 is located.
    plates: Specify which plates will be analysed e.g. [1, 2, 3] for the three left plates.
        Default (None) is to analyze all plates.
    """
    if plate_names is None:
        plate_names = ["tray1", "tray2", "tray3", "tray4", "tray5", "tray6"]

    wrong_plate_name_error = ValueError("Length of plate_names must correspond to length of plates")
    if plates is None:
        if len(plate_names) != 6:
            raise wrong_plate_name_error
    else:
        if len(plate_names) != len(plates):
            raise wrong_plate_name_error

    rows, columns = gp_align.plate_specs["rows_and_columns"][str(plate_type)]

    if plates is not None:
        raise NotImplementedError()

    if parse_dates:
        time_list, sorted_image_list = gp_align.parse_time.sort_filenames(image_list)
    else:
        time_list, sorted_image_list = list(range(len(image_list))), image_list

    data = {}

    calibration_name_left = "calibration_type_"+str(plate_type)+"_left"
    calibration_name_right = "calibration_type_"+str(plate_type)+"_right"
    calibration_left = skimage.io.imread(os.path.join(os.path.dirname(__file__), "data", calibration_name_left+".png"))
    calibration_right = skimage.io.imread(os.path.join(os.path.dirname(__file__), "data", calibration_name_right+".png"))

    calibration_left = calibration_left / calibration_left.max()  # Normalise to values between 0 and 1
    calibration_right = calibration_right / calibration_right.max()  # Normalise to values between 0 and 1

    calibration_left = skimage.feature.canny(calibration_left, CANNY_SIGMA)
    calibration_right = skimage.feature.canny(calibration_right, CANNY_SIGMA)

    for image_name in sorted_image_list:
        # print(image_name)
        image = skimage.io.imread(image_name)
        image = skimage.color.rgb2gray(image)

        plate_images = gp_align.util.split_image_in_n(image)

        for i, (plate_name, plate_image) in enumerate(zip(plate_names, plate_images)):
            if i // 3 == 0:
                calibration_plate = calibration_left
                calibration_name = calibration_name_left
            else:
                calibration_plate = calibration_right
                calibration_name = calibration_name_right

            edge_image = skimage.feature.canny(plate_image, CANNY_SIGMA)
            offset = gp_align.align.align_plates(edge_image, calibration_plate)  # Align the (edged) plate image with calibration to find the offset
            well_names = gp_align.util.list_of_well_names(rows, columns, orientation)

            plate_image = plate_image / (1-plate_image)

            well_centers = generate_well_centers(
                np.array(gp_align.plate_specs["plate_positions"][calibration_name]) + offset,  # Add the offset to get the well centers in the analyte plate
                gp_align.plate_specs["plate_size"],
                rows, columns
            )
            #print(offset)
            #for well_center in well_centers:
            #    offset_center = well_center
            #    plate_image[offset_center[0], offset_center[1]] = 1
            #skimage.#io.imshow(plate_image)
            #return 1
            #print(well_centers)

            assert len(well_centers) == rows * columns
            well_intensities = [find_well_intensity(plate_image, center) for center in well_centers]

            for well_name, intensity in zip(well_names, well_intensities):
                data.setdefault(plate_name, {}).setdefault(well_name, []).append(intensity)

    # Format the data
    output = {}
    for plate, plate_data in data.items():
        wells = gp_align.util.list_of_well_names(rows, columns, orientation="top_left")
        plate_df = pd.DataFrame(plate_data)
        assert len(plate_df.columns) == len(wells)
        plate_df = plate_df[wells]

        for col in plate_df:
            assert len(plate_df[col]) == len(time_list)
        plate_df.index = time_list
        output[plate] = plate_df

    return output


def generate_well_centers(position, size, rows, columns):
    """Returns a list of coordinates given an origin and plate size and dimensions"""
    xs = (np.arange(0, size[0], size[0] / (columns*2)) + position[0])[1::2]
    ys = (np.arange(0, size[1], size[1] / (rows*2)) + position[1])[1::2]
    return np.array([(int(round(x)), int(round(y))) for x in xs for y in ys])


def find_well_intensity(image, center, radius=4, n_mean=10):
    """Given an image and a position, finds the mean of the *n_mean* darkest pixels within *radius*"""
    im_slice = image[
        center[0]-radius: center[0]+radius+1,
        center[1]-radius: center[1]+radius+1
    ].flatten()
    im_slice.sort()
    darkest = np.percentile(im_slice[:n_mean], 50)
    return darkest

