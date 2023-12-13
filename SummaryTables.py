#!/usr/bin/env python

import sys,  string
from PyQt6 import QtCore,  QtGui,  QtWidgets
from ui import ui_SummaryTables
from MaceFunctions import connectdlg,  dbConnection
import numpy as np
from math import *
import csv

class SummaryTables(QtWidgets.QMainWindow, ui_SummaryTables.Ui_SummaryTables):

    def __init__(self, odbcSource, user, password, bio_schema, parent=None):
        super(SummaryTables, self).__init__(parent)
        self.setupUi(self)

        #  define some application variables
        self.resultsStart = None
        self.resultsEnd = None
        self.resultsGear = None
        self.resultsShip = None
        self.resultsSurvey = None


        #  store the variables we passed into our init method
        self.odbc = odbcSource
        self.dbUser = user
        self.dbPassword = password
        self.bioSchema = bio_schema

        #  restore the application state
        self.__appSettings = QtCore.QSettings('afsc.noaa.gov', 'SummaryTables')
        size = self.__appSettings.value('winsize', QtCore.QSize(940,800))
        self.resize(size)
        position = self.__appSettings.value('winposition', QtCore.QPoint(10,10))
        self.move(position)
        self.latestSurvey = self.__appSettings.value('latestSurvey','')
        self.dirName = self.__appSettings.value('saveDirectory','C://temp')

        #  connect signals/slots
        self.shipBox.activated[int].connect(self.getSurveys)
        self.surveyBox.activated[int].connect(self.getHauls)
        self.startHaulBox.activated[int].connect(self.paramsChanged)
        self.endHaulBox.activated[int].connect(self.paramsChanged)
        self.gearTypeBox.activated[int].connect(self.paramsChanged)
        self.nonRandomCheckBox1.stateChanged[int].connect(self.randomSpec)
        self.checkBox.stateChanged[int].connect(self.randomSpec)
        self.csvBtn1.clicked.connect(self.handleSave)
        self.csvBtn2.clicked.connect(self.handleSave)
        self.csvBtn3.clicked.connect(self.handleSave)
        self.runButton.clicked.connect(self.runQueries)
        

        #  add a label to the status bar to report query status
        self.statusLabel = QtWidgets.QLabel('')
        self.statusbar.addPermanentWidget(self.statusLabel)

        #  initially disable tab widget
        self.tabWidget.setEnabled(False)

        #  set the application icon
        try:
            self.setWindowIcon(QtGui.QIcon('./resources/question-icon-1.png'))
        except:
            pass

        #  fire a single shot timer to complete initialization in a separate methods
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self.applicationInit)
        timer.start(0)


    def randomSpec(self):
        if self.sender() == self.nonRandomCheckBox1:
            if self.nonRandomCheckBox1.isChecked():
                self.checkBox.setChecked(True)
            else:
                self.checkBox.setChecked(False)
        if self.sender() == self.checkBox:
            if self.checkBox.isChecked():
                self.nonRandomCheckBox1.setChecked(True)
            else:
                self.nonRandomCheckBox1.setChecked(False)
        self.makeTables()


    def paramsChanged(self):
        '''
        paramsChanged is called when the start/end hauls are changed or the gear type is
        changed. When these are changed we disable the tabs to indicate that the data in
        the tables IS NOT the data queried from the current ship/survey/haul/gear parameters.

        we also do a sanity check on the start and end hauls and adjust them accordingly
        '''

        #  first the sanity check - get the start and end haul indexes
        startIdx = self.startHaulBox.currentIndex()
        endIdx = self.endHaulBox.currentIndex()

        #  check if our start is before our end
        if (startIdx > endIdx):
            endIdx = startIdx

            #  now update the end combobox
            self.endHaulBox.setCurrentIndex(endIdx)

        #  assume we're good
        dataValid = True

        # then check current entries against our last queried values
        if (self.shipBox.currentText() != self.resultsShip):
            dataValid = False
        if (self.surveyBox.currentText() != self.resultsSurvey):
            dataValid = False
        if (self.startHaulBox.currentText() != self.resultsStart):
            dataValid = False
        if (self.endHaulBox.currentText() != self.resultsEnd):
            dataValid = False
        if (self.gearTypeBox.currentText() != self.resultsGear):
            dataValid = False

        #  enable/disable tab widget based on the result
        self.tabWidget.setEnabled(dataValid)


    def applicationInit(self):
        self.db = None

        #  check if we're missing any of our required connection parameters
        if ((self.odbc == None) or (self.dbUser == None) or
            (self.dbPassword == None)):

            #  we're missing at least one - display the connect dialog to get the rest of the args.
            #  Note the use of the new createConnection argument which keeps ConnectDlg from creating
            #  an instance of dbConnection. We'll do that below.
            #  Also note the new enableBioschema argument which will disable the bioschema combobox
            connectDlg = connectdlg.ConnectDlg(self.odbc, self.dbUser, self.dbPassword, label='SummaryTables',
                    bioSchema=self.bioSchema, enableBioschema=False, createConnection=False, parent=self)

            if not connectDlg.exec():
                #  user hit cancel so we exit this example program
                self.close()
                return

            #  update our connection credentials
            self.odbc = connectDlg.getSource()
            self.dbUser = connectDlg.getUsername()
            self.dbPassword = connectDlg.getPassword()
            self.bioSchema = connectDlg.getBioSchema()

        #  create the database connection
        self.db = dbConnection.dbConnection(self.odbc, self.dbUser,
                self.dbPassword, 'SummaryTables')

        #  store the bioSchema in the db object
        self.db.bioSchema=self.bioSchema

        try:
            #  attempt to connect to the database
            self.db.dbOpen()
        except dbConnection.DBError as e:
            #  ooops, there was a problem
            errorMsg = ('Unable to connect to ' + self.dbUser+ '@' +
                    self.odbc + '\n' + e.error)
            QtWidgets.QMessageBox.critical(self, "Databse Login Error", errorMsg)
            self.close()
            return

        #  perform our initial SHIP query
        if (self.db != None):
            query = self.db.dbQuery("SELECT " + self.db.bioSchema + ".ships.ship FROM " +
                    self.db.bioSchema + ".ships ORDER BY " + self.db.bioSchema + ".ships.ship")
            for ship, in query:
                self.shipBox.addItem(ship)
            self.shipBox.setCurrentIndex(self.shipBox.findText('157', QtCore.Qt.MatchFlag.MatchExactly))

            #  now query the surveys
            self.getSurveys()


    def getSurveys(self):

        #  first clear the survey combobox
        self.surveyBox.clear()

        #populate survey
        query = self.db.dbQuery("SELECT " + self.db.bioSchema + ".surveys.survey FROM " + self.db.bioSchema +
                ".surveys WHERE " + self.db.bioSchema + ".surveys.ship=" + self.shipBox.currentText() +
                " AND survey >= 201502 ORDER BY " + self.db.bioSchema + ".surveys.survey")
        for survey, in query:
            self.surveyBox.addItem(survey)
        if self.latestSurvey =='':
            self.surveyBox.setCurrentIndex(-1)
        else:
            self.surveyBox.setCurrentIndex(self.surveyBox.findText(self.latestSurvey, QtCore.Qt.MatchFlag.MatchExactly))
            self.getHauls()


    def getHauls(self):
        try:
            self.startHaulBox.clear()
            self.endHaulBox.clear()
            query = self.db.dbQuery("SELECT event_id FROM " + self.db.bioSchema + ".events " +
                    "WHERE " + self.db.bioSchema + ".events.SHIP=" + self.shipBox.currentText() +
                    " AND " + self.db.bioSchema + ".events.SURVEY=" + self.surveyBox.currentText() +
                    " ORDER BY " + self.db.bioSchema + ".events.event_id ASC")
            self.hauls=[]
            for event_id, in query:
                self.hauls.append(event_id)
                self.startHaulBox.addItem(event_id)
                self.endHaulBox.addItem(event_id)
            self.startHaulBox.setCurrentIndex(0)
            self.endHaulBox.setCurrentIndex(len(self.hauls)-1)
            self.gearTypeBox.clear()
            self.gearTypeBox.addItem('All')
            sq1 = ("SELECT EVENTS.GEAR FROM " + self.db.bioSchema + ".EVENTS WHERE ship= " +
                    self.shipBox.currentText() + " AND " + " survey=" + self.surveyBox.currentText() +
                    " GROUP BY GEAR")
            query = self.db.dbQuery(sq1)
            for gear in query:
                self.gearTypeBox.addItem(gear[0])

        except Exception as e:
            msg = ''.join(s for s in str(e) if s in string.printable)
            QtWidgets.QMessageBox.warning(self, "ERROR", msg)


    def runQueries(self):

        #  this takes a while so set the busy cursor
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.CursorShape.WaitCursor))

        #  update the "last query" parameters
        self.resultsShip = self.shipBox.currentText()
        self.resultsSurvey = self.surveyBox.currentText()
        self.resultsStart = self.startHaulBox.currentText()
        self.resultsEnd = self.endHaulBox.currentText()
        self.resultsGear = self.gearTypeBox.currentText()

        #  do the work
        self.surveyTotals()
        self.makeTables()

        #  enable tab widget in case it is currently disabled
        self.tabWidget.setEnabled(True)

        #  clear the status label
        self.statusLabel.setText('')

        #  reset the cursor
        QtWidgets.QApplication.restoreOverrideCursor()


    def updateStatusBar(self, text, color='0030FF'):
        '''
        updateStatusBar simply formats text for our status bar and because these updates
        usually happen in the middle of long running methods we force Qt to process the event
        queue to update the gui and actually draw our text
        '''
        self.statusLabel.setText('<span style=" color:#' + color + ';">' + text + '</span>')
        QtWidgets.QApplication.processEvents()


    def makeTables(self):

        #  define some local variables
        spec_species = []
        spec_common_name = []
        spec_subcat = []
        spec_part = []

        #  determine the sampling method
        if self.nonRandomCheckBox1.isChecked():
            samplingMethod = 'non_random'
        else:
            samplingMethod = 'random'

        #  build the query text
        query = self.db.dbQuery(" SELECT species_code, common_name, subcategory, partition" +
                " FROM " + self.db.bioSchema + ".v_specimen_measurements WHERE(ship= " + self.shipBox.currentText() +
                " AND survey= " + self.surveyBox.currentText() + " AND haul>=" + self.startHaulBox.currentText() +
                " AND  haul<= " + self.endHaulBox.currentText() + " AND sampling_method='" + samplingMethod + "')" +
                " GROUP BY species_code,common_name,subcategory,partition ORDER BY partition,species_code,subcategory")


        self.updateStatusBar('Querying specimen totals')
        for species, common_name, subcategory, partition in query:
            spec_species.append(species)
            spec_common_name.append(common_name)
            spec_subcat.append(subcategory)
            spec_part.append(partition)

        self.surveySpecimenTotalsTable.setRowCount(0)
        self.surveySpecimenTotalsTable.setColumnCount(10)

        for i in range(len(spec_species)):
            self.updateStatusBar('Querying specimen totals ' + str(i+1) + ' of ' + str(len(spec_species)+1) +
                    ': ' + spec_species[i])
            QtWidgets.QApplication.processEvents()

            query=self.db.dbQuery("SELECT parameter_value from "+self.db.bioSchema+".species_data " +
                                                    " WHERE species_code="+spec_species[i]+" AND (species_parameter='Primary_Length_Type' " +
                                                    " OR species_parameter='Secondary_Length_Type')")
            len_types=[]
            for LT in query:
                len_types.append(LT[0])

            if self.nonRandomCheckBox1.isChecked():
                query = self.db.dbQuery(" SELECT a.subcategory, a.organism_weight, a."+len_types[0]+", a."+len_types[1]+", a.barcode, a.ovary_taken, a.maturity "+
                "  FROM "+self.db.bioSchema+".v_specimen_measurements a "+
                " WHERE a.ship= " + self.shipBox.currentText() +  "  AND" +
                " a.survey= "+ self.surveyBox.currentText()+ " AND  a.haul>= " + self.startHaulBox.currentText()+" AND  a.haul<= " + self.endHaulBox.currentText()+
                " AND a.species_code = " + spec_species[i] +" AND a.subcategory = '" + spec_subcat[i] +"' AND a.partition = '"+spec_part[i]+"' and a.sampling_method = 'non_random'")
            else:
                query = self.db.dbQuery(" SELECT a.subcategory, a.organism_weight, a."+len_types[0]+", a."+len_types[1]+", a.barcode, a.ovary_taken, a.maturity "+
                "  FROM "+self.db.bioSchema+".v_specimen_measurements a "+
                " WHERE a.ship= " + self.shipBox.currentText() +  "  AND" +
                " a.survey= "+ self.surveyBox.currentText()+ " AND  a.haul>= " + self.startHaulBox.currentText()+" AND  a.haul<= " + self.endHaulBox.currentText()+
                " AND a.species_code = " + spec_species[i] +" AND a.subcategory = '" + spec_subcat[i] +"' AND a.partition = '"+spec_part[i]+"'")
            subcat = []
            oweight = []
            olength = []
            lengthed=[]
            otolith = []
            ovary = []
            LW=[]
            # Nulls come back as '0' (for numbers) and '' (for strings) so check before appending to lists where the mean is taken
            for subcategory, organism_weight, length1, length2, barcode, ovary_taken,  maturity in query:
                if length1 is not None:
                    length=length1
                else:
                    length=length2
                subcat.append(subcategory)
                if organism_weight is not None and float(organism_weight) > 0:
                    # all weights
                    oweight.append(float(organism_weight))
                    if barcode is None or int(barcode) == 0:
                        # if it is length-weight and not otoliths taken
                        LW.append(1)
                elif length is not None and float(length) > 0:
                    # compute numbers if there is no weight but there is a length
                    lengthed.append(1)
                # find all lengths
                    olength.append(float(length))
                else:
                    olength.append(0)
                if barcode is not None and int(barcode) > 0:
                    # count all otoliths taken
                    otolith.append(1)
                if ovary_taken == 'Yes':
                    # count all ovaries taken
                    ovary.append(1)

            # Determine numbers of each basket type (measure, toss, and count) for specimen table
            query = self.db.dbQuery(" SELECT a.basket_type as basket_type"+
            "  FROM "+self.db.bioSchema+".baskets a, "+self.db.bioSchema+".samples b WHERE " +
            " a.sample_id = b.sample_id AND a.event_id =b.event_id AND a.ship = b.ship AND a.survey = b.survey AND"
            " a.ship= " + self.shipBox.currentText() +  "  AND" +
            " a.survey= "+ self.surveyBox.currentText()+ " AND  a.event_id>= " + self.startHaulBox.currentText()+" AND  a.event_id<= " + self.endHaulBox.currentText()+
            " AND b.species_code = " + spec_species[i] +" AND b.subcategory = '" + spec_subcat[i] +"' AND b.partition = '"+spec_part[i]+"'")
            meas=[]
            count=[]
            toss=[]
            for basket_type in query:
                if basket_type == ['Measure']:
                    meas.append(1)
                if basket_type == ['Count']:
                    count.append(1)
                if basket_type == ['Toss']:
                    toss.append(1)

            # Determine average weight of each species calculated by total weight sampled / total numbers sampled
            # for comparison with average weight sampled from length-weight
            query = self.db.dbQuery(" SELECT sampled_weight, sampled_number "+
            "  FROM "+self.db.bioSchema+".catch_summary WHERE ship= " + self.shipBox.currentText() +  "  AND" +
            " survey= "+ self.surveyBox.currentText()+ " AND event_id>= " + self.startHaulBox.currentText()+" AND  event_id<= " + self.endHaulBox.currentText()+
            " AND species_code = " + spec_species[i] +" AND subcategory = '" + spec_subcat[i] +"' AND partition = '"+spec_part[i]+"'")

            tot_w=[]
            tot_n=[]
            for sampled_weight,  sampled_number in query:
                if sampled_weight is not None:
                    tot_w.append(float(sampled_weight))
                else:
                    tot_w.append(0)
                if sampled_number is not None:
                    tot_n.append(float(sampled_number))
                else:
                    tot_n.append(1e-10)
            ave_w=np.array(tot_w)/np.array(tot_n)


            # Find total numbers sampled
            tot_samp=sum(otolith)+sum(LW)+sum(lengthed)

            self.surveySpecimenTotalsTable.setRowCount(len(spec_species))
            self.surveySpecimenTotalsTable.setItem(i, 0, QtWidgets.QTableWidgetItem(spec_part[i]))
            self.surveySpecimenTotalsTable.setItem(i, 1, QtWidgets.QTableWidgetItem(spec_species[i]))
            self.surveySpecimenTotalsTable.setItem(i, 2, QtWidgets.QTableWidgetItem(spec_common_name[i]))
            self.surveySpecimenTotalsTable.setItem(i, 3, QtWidgets.QTableWidgetItem(spec_subcat[i]))
            self.surveySpecimenTotalsTable.setItem(i, 4, QtWidgets.QTableWidgetItem(str(np.mean(oweight).round(3))))
            self.surveySpecimenTotalsTable.setItem(i, 5, QtWidgets.QTableWidgetItem(str(ave_w[0].round(3))))
            self.surveySpecimenTotalsTable.setItem(i, 6, QtWidgets.QTableWidgetItem(str(np.mean(olength).round(3))))
            self.surveySpecimenTotalsTable.setItem(i, 7, QtWidgets.QTableWidgetItem((str(sum(meas))+"/"+str(sum(toss))+"/"+str(sum(count)))))
            self.surveySpecimenTotalsTable.setItem(i, 8, QtWidgets.QTableWidgetItem((str(tot_samp)+" ("+str(sum(otolith))+" , "+str(sum(LW))+" , "+str(sum(lengthed))+")")))
            self.surveySpecimenTotalsTable.setItem(i, 9, QtWidgets.QTableWidgetItem(str(sum(ovary))))
            self.surveySpecimenTotalsTable.setHorizontalHeaderLabels(['Partition', 'Species Code', 'Common Name','Subcategory', 'Mean W (From LW)', 'Mean W (From Tot W)', 'Ave. Length', 'Baskets (M/T/C)',  'Number Sampled (O , LW , L)', 'Ovaries'])
            self.surveySpecimenTotalsTable.setColumnWidth(4, 125)
            self.surveySpecimenTotalsTable.setColumnWidth(5, 125)
            self.surveySpecimenTotalsTable.setColumnWidth(8, 175)


        # maturity table
        self.updateStatusBar('Querying maturity totals')
        if self.nonRandomCheckBox1.isChecked():
            query1 = self.db.dbQuery(" SELECT sex,maturity " +
                "  FROM "+self.db.bioSchema+".v_specimen_measurements WHERE( ship= " + self.shipBox.currentText() +  "  AND" +
                " survey= "+ self.surveyBox.currentText()+ " AND  haul>= " + self.startHaulBox.currentText()+" AND  haul<= " + self.endHaulBox.currentText()+" and species_code = 21740 and maturity is not null and sampling_method = 'non_random')"+
                " GROUP BY  sex,maturity order by  sex,case maturity  WHEN 'Immature' THEN 1 "+
                " WHEN 'Developing' THEN 2 WHEN 'Prespawning' THEN 3 WHEN 'Spawning' THEN 4 WHEN 'Spent' THEN 5 END")
        else:
            query1 = self.db.dbQuery(" SELECT sex,maturity " +
            "  FROM "+self.db.bioSchema+".v_specimen_measurements WHERE( ship= " + self.shipBox.currentText() +  "  AND" +
            " survey= "+ self.surveyBox.currentText()+ " AND  haul>= " + self.startHaulBox.currentText()+" AND  haul<= " + self.endHaulBox.currentText()+" and species_code = 21740 and maturity is not null)"+
            " GROUP BY  sex,maturity order by  sex,case maturity  WHEN 'Immature' THEN 1 "+
            " WHEN 'Developing' THEN 2 WHEN 'Prespawning' THEN 3 WHEN 'Spawning' THEN 4 WHEN 'Spent' THEN 5 END")
        mat_maturity = []
        mat_sex = []
        for  sex, maturity in query1:
            mat_sex.append(sex)
            mat_maturity.append(maturity)

        num_tot_F=[]
        num_tot_F_40=[]
        num_tot_M=[]
        num_tot_M_40=[]
        t1=[]
        t2=[]
        t3=[]
        t4=[]

        if self.nonRandomCheckBox1.isChecked():
            # Query total of specimens for all females to determine percent in each maturity stage
            querya=self.db.dbQuery(" SELECT a.fork_length, a.standard_length "+
                    " FROM "+self.db.bioSchema+".v_specimen_measurements a "+
                    " WHERE a.ship= " + self.shipBox.currentText() +  "  AND " +
                    " a.survey= "+ self.surveyBox.currentText()+ " AND  a.haul>= " + self.startHaulBox.currentText()+" AND  a.haul<= " + self.endHaulBox.currentText()+
                    " AND a.species_code = 21740 AND a.sex = 'Female' and a.maturity is not null and a.sampling_method = 'non_random'")
            for length1, length2  in querya:
                if length1 is not None:
                    length=length1
                else:
                    length=length2
                t1.append(float(length))
            num_tot_F=float(len(t1))

            # Query total of specimens above 40 cm females to determine percent in each maturity stage
            queryb=self.db.dbQuery(" SELECT a.fork_length "+
                    "  FROM "+self.db.bioSchema+".v_specimen_measurements a "+
                    " WHERE a.ship= " + self.shipBox.currentText() +  "  AND" +
                    " a.survey= "+ self.surveyBox.currentText()+ " AND  a.haul>= " + self.startHaulBox.currentText()+" AND  a.haul<= " + self.endHaulBox.currentText()+
                    " AND a.species_code = 21740 AND a.fork_length > 40 AND a.sex = 'Female' and a.maturity is not null and a.sampling_method = 'non_random'")
            for length,  in queryb:
                t2.append(float(length))
            num_tot_F_40=float(len(t2))

            # Query total of specimens for all males to determine percent in each maturity stage
            querya=self.db.dbQuery(" SELECT a.fork_length, a.standard_length "+
                    " FROM "+self.db.bioSchema+".v_specimen_measurements a "+
                    " WHERE a.ship= " + self.shipBox.currentText() +  "  AND " +
                    " a.survey= "+ self.surveyBox.currentText()+ " AND  a.haul>= " + self.startHaulBox.currentText()+" AND  a.haul<= " + self.endHaulBox.currentText()+
                    " AND a.species_code = 21740 AND a.sex = 'Male' and a.maturity is not null and a.sampling_method = 'non_random'")
            for length1, length2  in querya:
                if length1 is not None:
                    length=length1
                else:
                    length=length2
                t3.append(float(length))
            num_tot_M=float(len(t3))

            # Query total of specimens above 40 cm females to determine percent in each maturity stage
            queryb=self.db.dbQuery(" SELECT a.fork_length "+
                    "  FROM "+self.db.bioSchema+".v_specimen_measurements a "+
                    " WHERE a.ship= " + self.shipBox.currentText() +  "  AND" +
                    " a.survey= "+ self.surveyBox.currentText()+ " AND  a.haul>= " + self.startHaulBox.currentText()+" AND  a.haul<= " + self.endHaulBox.currentText()+
                    " AND a.species_code = 21740 AND a.fork_length > 40 AND a.sex = 'Male' and a.maturity is not null and a.sampling_method = 'non_random'")
            for length,  in queryb:
                t4.append(float(length))
            num_tot_M_40=float(len(t4))

        else:
            # Query total of specimens for all females to determine percent in each maturity stage
            querya=self.db.dbQuery(" SELECT a.fork_length, a.standard_length "+
                    " FROM "+self.db.bioSchema+".v_specimen_measurements a "+
                    " WHERE a.ship= " + self.shipBox.currentText() +  "  AND " +
                    " a.survey= "+ self.surveyBox.currentText()+ " AND  a.haul>= " + self.startHaulBox.currentText()+" AND  a.haul<= " + self.endHaulBox.currentText()+
                    " AND a.species_code = 21740 AND a.sex = 'Female' and a.maturity is not null")
            for length1, length2  in querya:
                if length1 is not None:
                    length=length1
                else:
                    length=length2
                t1.append(float(length))
            num_tot_F=float(len(t1))

            # Query total of specimens above 40 cm females to determine percent in each maturity stage
            queryb=self.db.dbQuery(" SELECT a.fork_length "+
                    "  FROM "+self.db.bioSchema+".v_specimen_measurements a "+
                    " WHERE a.ship= " + self.shipBox.currentText() +  "  AND" +
                    " a.survey= "+ self.surveyBox.currentText()+ " AND  a.haul>= " + self.startHaulBox.currentText()+" AND  a.haul<= " + self.endHaulBox.currentText()+
                    " AND a.species_code = 21740 AND a.fork_length > 40 AND a.sex = 'Female' and a.maturity is not null")
            for length,  in queryb:
                t2.append(float(length))
            num_tot_F_40=float(len(t2))

            # Query total of specimens for all males to determine percent in each maturity stage
            querya=self.db.dbQuery(" SELECT a.fork_length, a.standard_length "+
                    " FROM "+self.db.bioSchema+".v_specimen_measurements a "+
                    " WHERE a.ship= " + self.shipBox.currentText() +  "  AND " +
                    " a.survey= "+ self.surveyBox.currentText()+ " AND  a.haul>= " + self.startHaulBox.currentText()+" AND  a.haul<= " + self.endHaulBox.currentText()+
                    " AND a.species_code = 21740 AND a.sex = 'Male' and a.maturity is not null")
            for length1, length2  in querya:
                if length1 is not None:
                    length=length1
                else:
                    length=length2
                t3.append(float(length))
            num_tot_M=float(len(t3))

            # Query total of specimens above 40 cm females to determine percent in each maturity stage
            queryb=self.db.dbQuery(" SELECT a.fork_length "+
                    "  FROM "+self.db.bioSchema+".v_specimen_measurements a "+
                    " WHERE a.ship= " + self.shipBox.currentText() +  "  AND" +
                    " a.survey= "+ self.surveyBox.currentText()+ " AND  a.haul>= " + self.startHaulBox.currentText()+" AND  a.haul<= " + self.endHaulBox.currentText()+
                    " AND a.species_code = 21740 AND a.fork_length > 40 AND a.sex = 'Male' and a.maturity is not null")
            for length,  in queryb:
                t4.append(float(length))
            num_tot_M_40=float(len(t4))


        self.surveyPollockTotalsTable.setRowCount(0)
        for i in range(len(mat_maturity)):
            if self.nonRandomCheckBox1.isChecked():
                # Query for all specimens
                query = self.db.dbQuery(" SELECT a.organism_weight, a.fork_length, a.standard_length, a.barcode, a.ovary_taken, a.maturity "+
                "  FROM "+self.db.bioSchema+".v_specimen_measurements a "+
                " WHERE a.ship= " + self.shipBox.currentText() +  "  AND" +
                " a.survey= "+ self.surveyBox.currentText()+ " AND  a.haul>= " + self.startHaulBox.currentText()+" AND  a.haul<= " + self.endHaulBox.currentText()+
                " AND a.species_code = 21740 AND a.maturity = '"+ mat_maturity[i] +"' AND a.sex = '"+ mat_sex[i] +"' and a.sampling_method = 'non_random'")
                # Query for specimens with lengths > 40 cm
                query2=self.db.dbQuery(" SELECT a.fork_length "+
                "  FROM "+self.db.bioSchema+".v_specimen_measurements a "+
                " WHERE a.ship= " + self.shipBox.currentText() +  "  AND" +
                " a.survey= "+ self.surveyBox.currentText()+ " AND  a.haul>= " + self.startHaulBox.currentText()+" AND  a.haul<= " + self.endHaulBox.currentText()+
                " AND a.species_code = 21740 AND a.maturity = '"+ mat_maturity[i] +"' AND a.sex = '"+ mat_sex[i] +"' and a.sampling_method = 'non_random' and a.fork_length > 40")
            else:
                # Query for all specimens
                query = self.db.dbQuery(" SELECT a.organism_weight, a.fork_length, a.standard_length, a.barcode, a.ovary_taken, a.maturity "+
            "  FROM "+self.db.bioSchema+".v_specimen_measurements a "+
            " WHERE a.ship= " + self.shipBox.currentText() +  "  AND" +
            " a.survey= "+ self.surveyBox.currentText()+ " AND  a.haul>= " + self.startHaulBox.currentText()+" AND  a.haul<= " + self.endHaulBox.currentText()+
            " AND a.species_code = 21740 AND a.maturity = '"+ mat_maturity[i] +"' AND a.sex = '"+ mat_sex[i] +"'")
            # Query for all specimens with lengths > 40 cm
                query2 = self.db.dbQuery(" SELECT a.fork_length "+
            "  FROM "+self.db.bioSchema+".v_specimen_measurements a "+
            " WHERE a.ship= " + self.shipBox.currentText() +  "  AND" +
            " a.survey= "+ self.surveyBox.currentText()+ " AND  a.haul>= " + self.startHaulBox.currentText()+" AND  a.haul<= " + self.endHaulBox.currentText()+
            " AND a.species_code = 21740 AND a.maturity = '"+ mat_maturity[i] +"' and a.fork_length > 40 AND a.sex = '"+ mat_sex[i] +"'")

            m_weight = []
            m_length = []
            m_perc = []
            m_length_40 = []
            m_perc_40 = []
            m_otolith = []
            m_ovary = []
            m_maturity=[]
            # Nulls come back as '0' (for numbers) and '' (for strings) so check before appending to lists where the mean is taken
            for organism_weight, length1, length2, barcode, ovary_taken, maturity in query:
                if length1 is not None:
                    length=length1
                else:
                    length=length2
                subcat.append(subcategory)
                if organism_weight is not None and float(organism_weight) > 0:
                    m_weight.append(float(organism_weight))
                m_length.append(float(length))
                if barcode is not None and int(barcode) > 0:
                    m_otolith.append(1)
                elif maturity != '':
                    m_maturity.append(1)
                if ovary_taken == 'Yes':
                    m_ovary.append(1)

            for length,  in query2:
                m_length_40.append(float(length))

            if mat_sex[i]=='Female':
                m_perc.append(np.array(len(m_length)/num_tot_F)*100)
                m_perc_40.append(np.array(len(m_length_40)/num_tot_F_40)*100)
            elif mat_sex[i]=='Male':
                m_perc.append(np.array(len(m_length)/num_tot_M)*100)
                m_perc_40.append(np.array(len(m_length_40)/num_tot_M_40)*100)

            self.surveyPollockTotalsTable.setColumnCount(12)
            self.surveyPollockTotalsTable.setRowCount(len(mat_maturity))
            self.surveyPollockTotalsTable.setItem(i,  0, QtWidgets.QTableWidgetItem("Walleye Pollock"))
            self.surveyPollockTotalsTable.setItem(i,  1, QtWidgets.QTableWidgetItem(mat_sex[i]))
            self.surveyPollockTotalsTable.setItem(i,  2, QtWidgets.QTableWidgetItem(mat_maturity[i]))
            self.surveyPollockTotalsTable.setItem(i,  3, QtWidgets.QTableWidgetItem(str(len(m_length))))
            self.surveyPollockTotalsTable.setItem(i,  4, QtWidgets.QTableWidgetItem(str(np.around(m_perc[0], decimals=1))))
            self.surveyPollockTotalsTable.setItem(i,  5, QtWidgets.QTableWidgetItem(str(len(m_length_40))))
            self.surveyPollockTotalsTable.setItem(i,  6, QtWidgets.QTableWidgetItem(str(np.around(m_perc_40[0], decimals=1))))
            self.surveyPollockTotalsTable.setItem(i,  7, QtWidgets.QTableWidgetItem(str(np.mean(m_weight).round(3))))
            self.surveyPollockTotalsTable.setItem(i,  8, QtWidgets.QTableWidgetItem(str(np.mean(m_length).round(3))))
            self.surveyPollockTotalsTable.setItem(i,  9, QtWidgets.QTableWidgetItem(str(sum(m_otolith))))
            self.surveyPollockTotalsTable.setItem(i,  10, QtWidgets.QTableWidgetItem(str(sum(m_maturity))))
            self.surveyPollockTotalsTable.setItem(i,  11, QtWidgets.QTableWidgetItem(str(sum(m_ovary))))
            self.surveyPollockTotalsTable.setHorizontalHeaderLabels(['Common Name', 'Sex','Maturity',
                    'Number Sampled', '% by Maturity',  'Number Sampled > 40cm','% by Maturity > 40cm',  'Ave. Weight', 'Ave. Length', 'Otoliths', 'LW GSI',  'Ovaries'])

        self.statusLabel.setText('')

    def surveyTotals(self):

        #  define local variables
        species = []
        name = []
        haulWeight = []
        sampWeight = []
        haulNum = []
        sampNum = []
        otoliths = []
        ovaries = []
        stomachs = []
        lens=[]
        weis=[]
        wt_percent = []
        num_percent = []

        #  build the query sql based on the gear type
        if self.gearTypeBox.currentText() == 'All':
            sql = ("select x.species_code, x.common_name,x.weight1, x.weight2, x.num1, x.num2, y.otolith, y.ovary, y.stomach, y.lengths1, y.lengths2, y.lengths3, y.lengths4, y.lengths5, y.lengths6, y.lengths7, y.lengths8, y.weights"+
                    " from (select ship,species_code, common_name, sum(weight_in_haul) as weight1, sum(sampled_weight) as weight2"+
                    " ,sum(number_in_haul) as num1,sum(sampled_number) as num2 from clamsbase2.catch_summary "
                    " where partition = 'Codend' and survey = "+self.surveyBox.currentText()+" and event_id >="+self.startHaulBox.currentText()+" and event_id <="+self.endHaulBox.currentText()+
                    " group by ship, survey,species_code, common_name) x"+
                    " join "+
                    " (select a.species_code, sum(case when a.barcode is not null then 1 end) as otolith,"+
                    " sum(case when a.ovary_taken = 'Yes' then 1 end) as ovary,"+
                    " sum(case when a.stomach_taken = 'Yes' then 1 end) as stomach, "+
                    " sum(case when a.fork_length is not null then 1 end) as lengths1, "+
                    " sum(case when a.standard_length is not null then 1 end) as lengths2, "+
                    " sum(case when a.total_length is not null then 1 end) as lengths3, "+
                    " sum(case when a.carapace_length is not null then 1 end) as lengths4, "+
                    " sum(case when a.bell_diameter is not null then 1 end) as lengths5, "+
                    " sum(case when a.wing_span is not null then 1 end) as lengths6, "+
                    " sum(case when a.mantle_length is not null then 1 end) as lengths7, "+
                    " sum(case when a.preanal_fin_length is not null then 1 end) as lengths8, "+
                    " sum(case when a.organism_weight is not null then 1 end) as weights from"+
                    " clamsbase2.v_specimen_measurements a "+
                    " where a.survey = "+self.surveyBox.currentText()+
                    " and a.partition = 'Codend' and a.haul >= "+self.startHaulBox.currentText()+
                    " and a.haul <="+self.endHaulBox.currentText()+
                    " and a.sampling_method = 'random' group by a.species_code) y"+
                    " on (x.species_code = y.species_code)"+
                    " order by x.weight1 desc")

        else:
            gear = self.gearTypeBox.currentText()
            sql = ("select event_id from clamsbase2.v_event_data where gear = '"+gear+"' and survey = "+self.surveyBox.currentText()+" and event_id >="+self.startHaulBox.currentText()+" and event_id <="+self.endHaulBox.currentText())
            query = self.db.dbQuery(sql)
            queryHauls = ''
            queryEvents = ''
            for haul in query:
                queryHauls = queryHauls + " a.haul = "+haul[0]+" or"
                queryEvents = queryEvents  + " event_id = "+haul[0]+" or"
            queryHauls = queryHauls[:-3]
            queryEvents = queryEvents[:-3]
            sql = ("select x.species_code, x.common_name,x.weight1, x.weight2, x.num1, x.num2, y.otolith, y.ovary, y.stomach, y.lengths1, y.lengths2, y.lengths3, y.lengths4, y.lengths5, y.lengths6, y.lengths7, y.lengths8, y.weights"+
                    " from (select ship,species_code, common_name, sum(weight_in_haul) as weight1, sum(sampled_weight) as weight2"+
                    " ,sum(number_in_haul) as num1,sum(sampled_number) as num2 from clamsbase2.catch_summary "
                    " where partition = 'Codend' and survey = "+self.surveyBox.currentText()+" and ("+queryEvents+") "+
                    " group by ship, survey,species_code, common_name) x"+
                    " join "+
                    " (select a.species_code, sum(case when a.barcode is not null then 1 end) as otolith,"+
                    " sum(case when a.ovary_taken = 'Yes' then 1 end) as ovary,"+
                    " sum(case when a.stomach_taken = 'Yes' then 1 end) as stomach, "+
                    " sum(case when a.fork_length is not null then 1 end) as lengths1, "+
                    " sum(case when a.standard_length is not null then 1 end) as lengths2, "+
                    " sum(case when a.total_length is not null then 1 end) as lengths3, "+
                    " sum(case when a.carapace_length is not null then 1 end) as lengths4, "+
                    " sum(case when a.bell_diameter is not null then 1 end) as lengths5, "+
                    " sum(case when a.wing_span is not null then 1 end) as lengths6, "+
                    " sum(case when a.mantle_length is not null then 1 end) as lengths7, "+
                    " sum(case when a.preanal_fin_length is not null then 1 end) as lengths8, "+
                    " sum(case when a.organism_weight is not null then 1 end) as weights from"+
                    " clamsbase2.v_specimen_measurements a "+
                    " where a.survey = "+self.surveyBox.currentText()+
                    " and a.partition = 'Codend' and ("+queryHauls+") "+
                    " group by a.species_code) y"+
                    " on (x.species_code = y.species_code)"+
                    " order by x.weight1 desc")

        #  query the database
        self.updateStatusBar('Querying survey catch totals')
        query = self.db.dbQuery(sql)

        #  and loop thru the results
        for species_code, common_name, weight1, weight2, num1, num2, otolith, ovary, stomach, lengths1, lengths2, lengths3, lengths4, lengths5, lengths6, lengths7, lengths8,  weights in query:

            species.append(species_code)
            name.append(common_name)
            haulWeight.append(weight1)
            sampWeight.append(weight2)
            haulNum.append(num1)
            sampNum.append(num2)

            # Added condition to take care of when there are no samples- in that case a None is returned
            if otolith is not None:
                otoliths.append(otolith)
            else:
                otoliths.append(0)
            if ovary is not None:
                ovaries.append(ovary)
            else:
                ovaries.append(0)
            if stomach is not None:
                stomachs.append(stomach)
            else:
                stomachs.append(0)
            Ls=[lengths1,lengths2,lengths3,lengths4,lengths5,lengths6,lengths7, lengths8]
            tot_L=[]
            for i in Ls:
                if i is not None:
                    tot_L.append(int(i))
            lens.append(sum(tot_L))
            if weights is not None:
                weis.append(weights)
            else:
                weis.append(0)
                
        #get a total weight and number
        tot_wt = sum(np.float64(haulWeight))
        tot_num = sum(np.float64(haulNum))
        
        #append total weight and number as percentages.
        for i in range(len(species)):
            wt_percent.append(str(np.around(np.float64(haulWeight[i])/tot_wt * 100,  decimals = 2)))
            num_percent.append(str(np.around(np.float64(haulNum[i])/tot_num * 100,  decimals = 2)))
            
              
        self.updateStatusBar('Updating survey catch totals table')
        for i in range(len(species)):
            self.surveyCatchTotalsTable.setColumnCount(13)
            self.surveyCatchTotalsTable.setRowCount(len(species))
            self.surveyCatchTotalsTable.setItem(i, 0, QtWidgets.QTableWidgetItem(species[i]))
            self.surveyCatchTotalsTable.setItem(i, 1, QtWidgets.QTableWidgetItem(name[i]))
            self.surveyCatchTotalsTable.setItem(i, 2, QtWidgets.QTableWidgetItem(haulWeight[i]))
            self.surveyCatchTotalsTable.setItem(i, 3, QtWidgets.QTableWidgetItem(sampWeight[i]))
            self.surveyCatchTotalsTable.setItem(i, 4, QtWidgets.QTableWidgetItem(str(wt_percent[i])))
            self.surveyCatchTotalsTable.setItem(i, 5, QtWidgets.QTableWidgetItem(haulNum[i]))
            self.surveyCatchTotalsTable.setItem(i, 6, QtWidgets.QTableWidgetItem(sampNum[i]))
            self.surveyCatchTotalsTable.setItem(i, 7, QtWidgets.QTableWidgetItem(num_percent[i]))
            self.surveyCatchTotalsTable.setItem(i, 8, QtWidgets.QTableWidgetItem(otoliths[i]))
            self.surveyCatchTotalsTable.setItem(i, 9, QtWidgets.QTableWidgetItem(str(lens[i])))
            self.surveyCatchTotalsTable.setItem(i, 10, QtWidgets.QTableWidgetItem(weis[i]))
            self.surveyCatchTotalsTable.setItem(i, 11, QtWidgets.QTableWidgetItem(ovaries[i]))
            self.surveyCatchTotalsTable.setItem(i, 12, QtWidgets.QTableWidgetItem(stomachs[i]))
            self.surveyCatchTotalsTable.setHorizontalHeaderLabels(['Species Code', 'Common Name','Total Weight',
                    'Sampled Weight',  '% By Weight', 'Total Number', 'Sampled Number', '% By Number','Otoliths', 'Lengths', 'Weights',
                    'Ovaries', 'Stomachs'])
            self.statusLabel.setText('')

    def getCommonName(self, code):
        query = self.db.dbQuery("SELECT common_name FROM "+self.db.bioSchema+".species WHERE species_code="+code)
        return query.first()[0]


    def handleSave(self):
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.CursorShape.WaitCursor))
        if self.tabWidget.currentIndex() ==0:
            table = self.surveyCatchTotalsTable
            header = ['Species Code', 'Common Name', 'Total Weight', 'Sampled Weight', 'Total Number', 'Sampled Number', 'Otoliths', 'Lengths', 'Weights',  'Ovaries', 'Stomachs']
        elif self.tabWidget.currentIndex() ==1:
            table = self.surveySpecimenTotalsTable
            header = ['Partition', 'Species Code', 'Common Name', 'Subcategory', 'Mean W (From LW)', 'Mean W (From Tot W)',
                    'Ave. Length', 'Baskets (M/T/C)', 'Number Sampled (O,LW,L)', 'Ovaries']
        elif self.tabWidget.currentIndex() ==2:
            table = self.surveyPollockTotalsTable
            header = ['Common Name', 'Sex', 'Maturity', 'Number Sampled', '% by Maturity',  'Number Sampled > 40cm',  '% by Maturity > 40cm',  'Ave. Weight', 'Ave. Length', 'Otoliths', 'LW GSI', 'Ovaries']
        path = QtWidgets.QFileDialog.getSaveFileName(
                self, 'Save File', '', 'CSV(*.csv)')
        if len(path[0])>0:
            with open(path[0], 'w', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(header)
                for row in range(table.rowCount()):
                    rowdata = []
                    for column in range(table.columnCount()):
                        item = table.item(row, column)
                        if item is not None:
                            rowdata.append(item.text())
                        else:
                            rowdata.append('')
                    writer.writerow(rowdata)
        QtWidgets.QApplication.restoreOverrideCursor()


    def closeEvent(self, event):

        #  update the application settings
        self.__appSettings.setValue('winposition', self.pos())
        self.__appSettings.setValue('winsize', self.size())
        self.__appSettings.setValue('latestSurvey', self.surveyBox.currentText())
        self.__appSettings.setValue('saveDirectory', self.dirName)


        if (not self.db == None):
            #  close the db connection
            self.db.dbClose()

        event.accept()


if __name__ == "__main__":

    '''
    PARSE THE COMMAND LINE ARGS
    '''
    import argparse

    #  specify the default credential and schema values
    bio_schema = "clamsbase2"
    odbc_connection = None
    username = None
    password = None

     #  create the argument parser. Set the application description.
    parser = argparse.ArgumentParser(description='SummaryTables')

    #  specify the positional arguments: ODBC connection, username, password
    parser.add_argument("odbc_connection", nargs='?', help="The name of the ODBC connection used to connect to the database.")
    parser.add_argument("username", nargs='?', help="The username used to log into the database.")
    parser.add_argument("password", nargs='?', help="The password for the specified username.")

    #  specify optional keyword arguments
    parser.add_argument("-b", "--bio_schema", help="Specify the biological database schema to use.")

    #  parse our arguments
    args = parser.parse_args()

    #  and assign to our vars (and convert from unicode to standard strings)
    if (args.bio_schema):
        #  strip off the leading space (if any)
        bio_schema = str(args.bio_schema).strip()
    if (args.odbc_connection):
        odbc_connection = str(args.odbc_connection)
    if (args.username):
        username = str(args.username)
    if (args.password):
        password = str(args.password)

    app = QtWidgets.QApplication(sys.argv)
    form = SummaryTables(odbc_connection, username, password, bio_schema)
    form.show()
    app.exec()

