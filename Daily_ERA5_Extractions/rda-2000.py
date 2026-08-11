#!/usr/bin/env python
""" 
Python script to download selected files from rda.ucar.edu.
After you save the file, don't forget to make it executable
i.e. - "chmod 755 <name_of_script>"
"""
import sys, os
from urllib.request import build_opener

opener = build_opener()

filelist = [
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200001/e5.oper.an.sfc.128_167_2t.ll025sc.2000010100_2000013123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200002/e5.oper.an.sfc.128_167_2t.ll025sc.2000020100_2000022923.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200003/e5.oper.an.sfc.128_167_2t.ll025sc.2000030100_2000033123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200004/e5.oper.an.sfc.128_167_2t.ll025sc.2000040100_2000043023.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200005/e5.oper.an.sfc.128_167_2t.ll025sc.2000050100_2000053123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200006/e5.oper.an.sfc.128_167_2t.ll025sc.2000060100_2000063023.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200007/e5.oper.an.sfc.128_167_2t.ll025sc.2000070100_2000073123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200008/e5.oper.an.sfc.128_167_2t.ll025sc.2000080100_2000083123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200009/e5.oper.an.sfc.128_167_2t.ll025sc.2000090100_2000093023.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200010/e5.oper.an.sfc.128_167_2t.ll025sc.2000100100_2000103123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200011/e5.oper.an.sfc.128_167_2t.ll025sc.2000110100_2000113023.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200012/e5.oper.an.sfc.128_167_2t.ll025sc.2000120100_2000123123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200001/e5.oper.an.sfc.128_168_2d.ll025sc.2000010100_2000013123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200002/e5.oper.an.sfc.128_168_2d.ll025sc.2000020100_2000022923.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200003/e5.oper.an.sfc.128_168_2d.ll025sc.2000030100_2000033123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200004/e5.oper.an.sfc.128_168_2d.ll025sc.2000040100_2000043023.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200005/e5.oper.an.sfc.128_168_2d.ll025sc.2000050100_2000053123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200006/e5.oper.an.sfc.128_168_2d.ll025sc.2000060100_2000063023.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200007/e5.oper.an.sfc.128_168_2d.ll025sc.2000070100_2000073123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200008/e5.oper.an.sfc.128_168_2d.ll025sc.2000080100_2000083123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200009/e5.oper.an.sfc.128_168_2d.ll025sc.2000090100_2000093023.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200010/e5.oper.an.sfc.128_168_2d.ll025sc.2000100100_2000103123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200011/e5.oper.an.sfc.128_168_2d.ll025sc.2000110100_2000113023.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200012/e5.oper.an.sfc.128_168_2d.ll025sc.2000120100_2000123123.nc'
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200001/e5.oper.an.sfc.128_134_sp.ll025sc.2000010100_2000013123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200002/e5.oper.an.sfc.128_134_sp.ll025sc.2000020100_2000022923.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200003/e5.oper.an.sfc.128_134_sp.ll025sc.2000030100_2000033123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200004/e5.oper.an.sfc.128_134_sp.ll025sc.2000040100_2000043023.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200005/e5.oper.an.sfc.128_134_sp.ll025sc.2000050100_2000053123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200006/e5.oper.an.sfc.128_134_sp.ll025sc.2000060100_2000063023.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200007/e5.oper.an.sfc.128_134_sp.ll025sc.2000070100_2000073123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200008/e5.oper.an.sfc.128_134_sp.ll025sc.2000080100_2000083123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200009/e5.oper.an.sfc.128_134_sp.ll025sc.2000090100_2000093023.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200010/e5.oper.an.sfc.128_134_sp.ll025sc.2000100100_2000103123.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200011/e5.oper.an.sfc.128_134_sp.ll025sc.2000110100_2000113023.nc',
  'https://data.rda.ucar.edu/d633000/e5.oper.an.sfc/200012/e5.oper.an.sfc.128_134_sp.ll025sc.2000120100_2000123123.nc'
]

for file in filelist:
    ofile = os.path.basename(file)
    sys.stdout.write("downloading " + ofile + " ... ")
    sys.stdout.flush()
    infile = opener.open(file)
    outfile = open(ofile, "wb")
    outfile.write(infile.read())
    outfile.close()
    sys.stdout.write("done\n")
