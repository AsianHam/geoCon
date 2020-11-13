from qgis.core import *
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from osgeo import gdal, osr
import numpy as np
import os, glob, datetime, sys, math, qgis.utils
import clawpack.pyclaw.solution as solution 

def main(sol, extension):
    qgs = QgsApplication([], False)
    qgs.initQgis()
    render(qgs, sol, extension)
    qgs.exitQgis()

#def main(extension):
def render(qgs, sol, extension):
    #QgsApplication.setPrefixPath('/usr/bin/qgis', True)
    qgs.setPrefixPath('/usr/bin/qgis', True)
    #qgs = QgsApplication([], False)
    #qgs.initQgis()
    extension = str(extension)
    print('the extension is:', extension)

    #sol = solution.Solution(int(extension))

    #first read through to determine certain values present in the file
    maxVal = 0
    minVal = 0
    mindx = 100
    mindy = 100

    dt = datetime.datetime.now().strftime('%m-%d_%H-%M')

    directory = extension + ' ' + dt + '/'
    if not os.path.exists(directory):
        os.makedirs(directory)

    fnBase = 'qraster.tif'
    driver = gdal.GetDriverByName('GTiff')
    rData = {}
    hData = {}          #header data - [amr, mx, my, xlow, mx*dx, ylow+my*dy, my*dy]
    amr = {}            #amr levels tying level to file/grid number

    for state in sol.states:
        #set dict with grid num as key to empty list
        gn = state.patch.patch_index
        rData[gn] = []
        hData[gn] = []   

        rValues = []
        hValues = []

        hData[gn].append(state.patch.level)                         #AMR level

        hData[gn].append(state.patch.dimensions[0].num_cells)       #mx
        hData[gn].append(state.patch.dimensions[1].num_cells)       #my

        hData[gn].append(state.patch.dimensions[0].lower)           #xlow
        hData[gn].append(state.patch.dimensions[1].upper)           #yhigh

        hData[gn].append(state.patch.dimensions[0].delta)           #dx
        hData[gn].append(state.patch.dimensions[1].delta)           #dy
        if state.patch.dimensions[0].delta < mindx:
            mindx = state.patch.dimensions[0].delta                 #smallest dx across all patches
        if state.patch.dimensions[1].delta < mindy:
            mindy = state.patch.dimensions[1].delta                 #smallest dy across all patches

        for i in range(state.patch.dimensions[0].num_cells):
            values = []
            for j in range(state.patch.dimensions[1].num_cells):
                if state.q[0, i, j] != 0:                           #check if depth is 0
                    values.append(state.q[3, i, j])
                    if state.q[3, i, j] > maxVal:                   #largest data value
                        maxVal = state.q[3, i, j]
                    elif state.q[3, i, j] < minVal:                 #smallest data value
                        minVal = state.q[3, i, j]
                elif state.q[0, i, j] == 0:
                    values.append(None)                             #append None type if depth is 0
            
            rValues.append(values)

        rData[gn] = rValues

    for key, items in rData.items():
        amrVal = hData[key][0]  #amr level
        xMax = hData[key][1]    #mx header
        yMax = hData[key][2]    #my header
        xlow = hData[key][3]    #xlow header
        yhigh = hData[key][4]   #yhigh header
        width = hData[key][5]   #dx headers
        height = hData[key][6]  #dy headers

        fArray = rData[key]
        
        fName = directory + str(key) + fnBase
        fTemp = directory + str(key) + 'temp' + fnBase
        fNameFin = directory + str(key) + 'fin' + fnBase
        
        if amrVal in amr.keys():
            amr[amrVal].append(fName)
            
        else:
            amr[amrVal] = []
            amr[amrVal].append(fName)
            
        ds = driver.Create(fName, xsize=xMax, ysize=yMax, bands=1, eType=gdal.GDT_Float32)
        if ds is None:
            return
        ndv = -100                                                        #The designated no data value
        band = ds.GetRasterBand(1).ReadAsArray()
        
        #v = 0
        try:
            for i in range(yMax):                                           #row then column
                for j in range(xMax):                           
                    if fArray[j][i] is None:
                        band[yMax-i-1][j] = ndv                             #set value to no data, thus making it transparent
                    else:
                        band[yMax-i-1][j] = fArray[j][i]

                    ds.GetRasterBand(1).WriteArray(band)
                    #v += 1
    
            geot = [xlow, width, 0, yhigh, 0, -1*height]
            ds.SetGeoTransform(geot)
            ds = None

            #reset color map
            rlayer = QgsRasterLayer(fName)
            provider = rlayer.dataProvider()
            provider.setNoDataValue(1, ndv)
            extent = rlayer.extent()
            stats = provider.bandStatistics(1, QgsRasterBandStats.All, extent, 0)
            pipe = QgsRasterPipe()

            width, height = rlayer.width(), rlayer.height()    

            fcn = QgsColorRampShader()
            fcn.setColorRampType(QgsColorRampShader.Interpolated)

            midVal = (maxVal + minVal) / 2

            lst = [QgsColorRampShader.ColorRampItem(minVal, QColor(0, 0, 255)),
                    QgsColorRampShader.ColorRampItem(midVal, QColor(0, 255, 255)),
                    QgsColorRampShader.ColorRampItem(maxVal, QColor(255, 0, 0))]

            fcn.setColorRampItemList(lst)
            shader = QgsRasterShader()
            shader.setRasterShaderFunction(fcn)

            renderer = QgsSingleBandPseudoColorRenderer(rlayer.dataProvider(), 1, shader)
            rlayer.setRenderer(renderer)
            rlayer.triggerRepaint()

            pipe.set(provider.clone())
            pipe.set(renderer.clone())

            write = QgsRasterFileWriter(fNameFin)
            write.writeRaster(pipe, width, height, extent, rlayer.crs())

        except Exception as ex:
            if type(ex) == IndexError:
                print(ex)
                continue
            else:
                print(ex)
                print(fArray[0][1])
                print(fArray[j][i+1])
                print(band[yMax-i-1][j])

                break

    #Merge tifs into one final tif
    sys.path.append('/usr/bin/')
    import gdal_merge as gm

    orderedFiles = ['', '-o', directory + '0' + extension + '.tif', '-ps', str(mindx), str(mindy)]

    for key, val in sorted(amr.items()):
        for i in val:
            f = i[:-11]
            orderedFiles.append(f + 'finqraster.tif')

    sys.argv = orderedFiles
    gm.main()

    print('\nThe rasterization is complete. The file name is', '0'+extension+'.tif')
    return
    #qgs.exitQgis()

if __name__ == '__main__':
    ext = input('Type the file you want to render: ')     #e.g. 9
    main(ext)