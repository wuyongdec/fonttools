# Copyright 2013 Google, Inc. All Rights Reserved.
#
# Google Author(s): Behdad Esfahbod, Roozbeh Pournader

"""Font merger.
"""

from __future__ import print_function, division
from fontTools.misc.py23 import *
from fontTools import ttLib, cffLib
from fontTools.ttLib.tables import otTables, _h_e_a_d
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from functools import reduce
import sys
import time
import operator


def _add_method(*clazzes, **kwargs):
	"""Returns a decorator function that adds a new method to one or
	more classes."""
	def wrapper(method):
		for clazz in clazzes:
			if not kwargs.get('allowDefaultTable', False):
				assert clazz != DefaultTable, 'Oops, table class not found.'
			assert method.__name__ not in clazz.__dict__, \
				"Oops, class '%s' has method '%s'." % (clazz.__name__,
								       method.__name__)
			setattr(clazz, method.__name__, method)
		return None
	return wrapper

# General utility functions for merging values from different fonts
def equal(lst):
	t = iter(lst)
	first = next(t)
	assert all(item == first for item in t)
	return first

def first(lst):
	return next(iter(lst))

def recalculate(lst):
	# Just return the first value, assume will be recalculated when saved
	return first(lst)

def current_time(lst):
	return int(time.time() - _h_e_a_d.mac_epoch_diff)

def bitwise_or(lst):
	return reduce(operator.or_, lst)

def ignore(lst):
	assert False, "This function should not be called."

def maybenone(func):
	"""Returns a filter func that when called with a list,
	only calls func on the non-None items of the list, and
	only so if there's at least one non-None item in the
	list."""

	def wrapper(lst):
		items = [item for item in lst if item is not None]
		return func(items) if items else None

	return wrapper

def sumLists(lst):
	l = []
	for item in lst:
		l.extend(item)
	return l

def sumDicts(lst):
	d = {}
	for item in lst:
		d.update(item)
	return d


@_add_method(DefaultTable, allowDefaultTable=True)
def merge(self, m, tables):
	if not hasattr(self, 'mergeMap'):
		m.log("Don't know how to merge '%s'." % self.tableTag)
		return False

	m._mergeKeys(self, self.mergeMap, tables)
	return True

ttLib.getTableClass('maxp').mergeMap = {
	'*': max,
	'tableTag': equal,
	'tableVersion': equal,
	'numGlyphs': sum,
	'maxStorage': max, # FIXME: may need to be changed to sum
	'maxFunctionDefs': sum,
	'maxInstructionDefs': sum,
	# TODO When we correctly merge hinting data, update these values:
	# maxFunctionDefs, maxInstructionDefs, maxSizeOfInstructions
}

ttLib.getTableClass('head').mergeMap = {
	'tableTag': equal,
	'tableVersion': max,
	'fontRevision': max,
	'checkSumAdjustment': recalculate,
	'magicNumber': equal,
	'flags': first, # FIXME: replace with bit-sensitive code
	'unitsPerEm': equal,
	'created': current_time,
	'modified': current_time,
	'xMin': min,
	'yMin': min,
	'xMax': max,
	'yMax': max,
	'macStyle': first,
	'lowestRecPPEM': max,
	'fontDirectionHint': lambda lst: 2,
	'indexToLocFormat': recalculate,
	'glyphDataFormat': equal,
}

ttLib.getTableClass('hhea').mergeMap = {
	'*': equal,
	'tableTag': equal,
	'tableVersion': max,
	'ascent': max,
	'descent': min,
	'lineGap': max,
	'advanceWidthMax': max,
	'minLeftSideBearing': min,
	'minRightSideBearing': min,
	'xMaxExtent': max,
	'caretSlopeRise': first, # FIXME
	'caretSlopeRun': first, # FIXME
	'caretOffset': first, # FIXME
	'numberOfHMetrics': recalculate,
}

ttLib.getTableClass('OS/2').mergeMap = {
	'*': first,
	'tableTag': equal,
	'version': max,
	'xAvgCharWidth': recalculate,
	'fsType': first, # FIXME
	'panose': first, # FIXME?
	'ulUnicodeRange1': bitwise_or,
	'ulUnicodeRange2': bitwise_or,
	'ulUnicodeRange3': bitwise_or,
	'ulUnicodeRange4': bitwise_or,
	'fsFirstCharIndex': min,
	'fsLastCharIndex': max,
	'sTypoAscender': max,
	'sTypoDescender': min,
	'sTypoLineGap': max,
	'usWinAscent': max,
	'usWinDescent': max,
	'ulCodePageRange1': bitwise_or,
	'ulCodePageRange2': bitwise_or,
	'usMaxContex': max,
	# TODO version 5
}

ttLib.getTableClass('post').mergeMap = {
	'*': first,
	'tableTag': equal,
	'formatType': max,
	'isFixedPitch': min,
	'minMemType42': max,
	'maxMemType42': lambda lst: 0,
	'minMemType1': max,
	'maxMemType1': lambda lst: 0,
	'mapping': ignore,
	'extraNames': ignore,
}
@_add_method(ttLib.getTableClass('post'))
def merge(self, m, tables):
	DefaultTable.merge(self, m, tables)
	self.mapping = {}
	for table in tables:
		if hasattr(table, 'mapping'):
			self.mapping.update(table.mapping)
	self.extraNames = []
	return True

ttLib.getTableClass('vmtx').mergeMap = ttLib.getTableClass('hmtx').mergeMap = {
	'tableTag': equal,
	'metrics': sumDicts,
}

ttLib.getTableClass('loca').mergeMap = {
	'*': ignore,
	'tableTag': equal,
}

ttLib.getTableClass('glyf').mergeMap = {
	'tableTag': equal,
	'glyphs': sumDicts,
	'glyphOrder': sumLists,
}

@_add_method(ttLib.getTableClass('glyf'))
def merge(self, m, tables):
	for table in tables:
		for g in table.glyphs.values():
			# Drop hints for now, since we don't remap
			# functions / CVT values.
			g.removeHinting()
			# Expand composite glyphs to load their
			# composite glyph names.
			if g.isComposite():
				g.expand(table)
	DefaultTable.merge(self, m, tables)
	return True

@_add_method(ttLib.getTableClass('prep'),
	     ttLib.getTableClass('fpgm'),
	     ttLib.getTableClass('cvt '))
def merge(self, m):
	return False # TODO We don't merge hinting data currently.

@_add_method(ttLib.getTableClass('cmap'))
def merge(self, m, tables):
	# TODO Handle format=14.
	cmapTables = [t for table in tables for t in table.tables
		      if t.platformID == 3 and t.platEncID in [1, 10]]
	# TODO Better handle format-4 and format-12 coexisting in same font.
	# TODO Insert both a format-4 and format-12 if needed.
	module = ttLib.getTableModule('cmap')
	assert all(t.format in [4, 12] for t in cmapTables)
	format = max(t.format for t in cmapTables)
	cmapTable = module.cmap_classes[format](format)
	cmapTable.cmap = {}
	cmapTable.platformID = 3
	cmapTable.platEncID = max(t.platEncID for t in cmapTables)
	cmapTable.language = 0
	for table in cmapTables:
		# TODO handle duplicates.
		cmapTable.cmap.update(table.cmap)
	self.tableVersion = 0
	self.tables = [cmapTable]
	self.numSubTables = len(self.tables)
	return True

@_add_method(ttLib.getTableClass('GDEF'))
def merge(self, m, tables):
	self.table = otTables.GDEF()
	self.table.Version = 1.0 # TODO version 1.2...

	if any(t.table.LigCaretList for t in tables):
		glyphs = []
		ligGlyphs = []
		for table in tables:
			if table.table.LigCaretList:
				glyphs.extend(table.table.LigCaretList.Coverage.glyphs)
				ligGlyphs.extend(table.table.LigCaretList.LigGlyph)
		coverage = otTables.Coverage()
		coverage.glyphs = glyphs
		ligCaretList = otTables.LigCaretList()
		ligCaretList.Coverage = coverage
		ligCaretList.LigGlyph = ligGlyphs
		ligCaretList.GlyphCount = len(ligGlyphs)
		self.table.LigCaretList = ligCaretList
	else:
		self.table.LigCaretList = None

	if any(t.table.MarkAttachClassDef for t in tables):
		classDefs = {}
		for table in tables:
			if table.table.MarkAttachClassDef:
				classDefs.update(table.table.MarkAttachClassDef.classDefs)
		self.table.MarkAttachClassDef = otTables.MarkAttachClassDef()
		self.table.MarkAttachClassDef.classDefs = classDefs
	else:
		self.table.MarkAttachClassDef = None

	if any(t.table.GlyphClassDef for t in tables):
		classDefs = {}
		for table in tables:
			if table.table.GlyphClassDef:
				classDefs.update(table.table.GlyphClassDef.classDefs)
		self.table.GlyphClassDef = otTables.GlyphClassDef()
		self.table.GlyphClassDef.classDefs = classDefs
	else:
		self.table.GlyphClassDef = None

	if any(t.table.AttachList for t in tables):
		glyphs = []
		attachPoints = []
		for table in tables:
			if table.table.AttachList:
				glyphs.extend(table.table.AttachList.Coverage.glyphs)
				attachPoints.extend(table.table.AttachList.AttachPoint)
		coverage = otTables.Coverage()
		coverage.glyphs = glyphs
		attachList = otTables.AttachList()
		attachList.Coverage = coverage
		attachList.AttachPoint = attachPoints
		attachList.GlyphCount = len(attachPoints)
		self.table.AttachList = attachList
	else:
		self.table.AttachList = None

	return True


class Options(object):

  class UnknownOptionError(Exception):
    pass

  _drop_tables_default = ['fpgm', 'prep', 'cvt ', 'gasp']
  drop_tables = _drop_tables_default

  def __init__(self, **kwargs):

    self.set(**kwargs)

  def set(self, **kwargs):
    for k,v in kwargs.items():
      if not hasattr(self, k):
        raise self.UnknownOptionError("Unknown option '%s'" % k)
      setattr(self, k, v)

  def parse_opts(self, argv, ignore_unknown=False):
    ret = []
    opts = {}
    for a in argv:
      orig_a = a
      if not a.startswith('--'):
        ret.append(a)
        continue
      a = a[2:]
      i = a.find('=')
      op = '='
      if i == -1:
        if a.startswith("no-"):
          k = a[3:]
          v = False
        else:
          k = a
          v = True
      else:
        k = a[:i]
        if k[-1] in "-+":
          op = k[-1]+'='  # Ops is '-=' or '+=' now.
          k = k[:-1]
        v = a[i+1:]
      k = k.replace('-', '_')
      if not hasattr(self, k):
        if ignore_unknown == True or k in ignore_unknown:
          ret.append(orig_a)
          continue
        else:
          raise self.UnknownOptionError("Unknown option '%s'" % a)

      ov = getattr(self, k)
      if isinstance(ov, bool):
        v = bool(v)
      elif isinstance(ov, int):
        v = int(v)
      elif isinstance(ov, list):
        vv = v.split(',')
        if vv == ['']:
          vv = []
        vv = [int(x, 0) if len(x) and x[0] in "0123456789" else x for x in vv]
        if op == '=':
          v = vv
        elif op == '+=':
          v = ov
          v.extend(vv)
        elif op == '-=':
          v = ov
          for x in vv:
            if x in v:
              v.remove(x)
        else:
          assert 0

      opts[k] = v
    self.set(**opts)

    return ret


class Merger(object):

	def __init__(self, options=None, log=None):

		if not log:
			log = Logger()
		if not options:
			options = Options()

		self.options = options
		self.log = log

	def merge(self, fontfiles):

		mega = ttLib.TTFont()

		#
		# Settle on a mega glyph order.
		#
		fonts = [ttLib.TTFont(fontfile) for fontfile in fontfiles]
		glyphOrders = [font.getGlyphOrder() for font in fonts]
		megaGlyphOrder = self._mergeGlyphOrders(glyphOrders)
		# Reload fonts and set new glyph names on them.
		# TODO Is it necessary to reload font?  I think it is.  At least
		# it's safer, in case tables were loaded to provide glyph names.
		fonts = [ttLib.TTFont(fontfile) for fontfile in fontfiles]
		for font,glyphOrder in zip(fonts, glyphOrders):
			font.setGlyphOrder(glyphOrder)
		mega.setGlyphOrder(megaGlyphOrder)

		allTags = reduce(set.union, (list(font.keys()) for font in fonts), set())
		allTags.remove('GlyphOrder')
		for tag in allTags:

			if tag in self.options.drop_tables:
				self.log("Dropping '%s'." % tag)
				continue

			clazz = ttLib.getTableClass(tag)

			# TODO For now assume all fonts have the same tables.
			tables = [font[tag] for font in fonts]
			table = clazz(tag)
			if table.merge (self, tables):
				mega[tag] = table
				self.log("Merged '%s'." % tag)
			else:
				self.log("Dropped '%s'." % tag)
			self.log.lapse("merge '%s'" % tag)

		return mega

	def _mergeGlyphOrders(self, glyphOrders):
		"""Modifies passed-in glyphOrders to reflect new glyph names.
		Returns glyphOrder for the merged font."""
		# Simply append font index to the glyph name for now.
		# TODO Even this simplistic numbering can result in conflicts.
		# But then again, we have to improve this soon anyway.
		mega = []
		for n,glyphOrder in enumerate(glyphOrders):
			for i,glyphName in enumerate(glyphOrder):
				glyphName += "#" + repr(n)
				glyphOrder[i] = glyphName
				mega.append(glyphName)
		return mega

	def _mergeKeys(self, return_table, logic, tables):
		allKeys = set.union(set(), *(vars(table).keys() for table in tables))
		for key in allKeys:
			try:
				merge_logic = logic[key]
			except KeyError:
				try:
					merge_logic = logic['*']
				except KeyError:
					raise Exception("Don't know how to merge key %s" % key)
			if merge_logic == ignore:
				continue
			key_value = merge_logic(getattr(table, key) for table in tables)
			setattr(return_table, key, key_value)


class Logger(object):

  def __init__(self, verbose=False, xml=False, timing=False):
    self.verbose = verbose
    self.xml = xml
    self.timing = timing
    self.last_time = self.start_time = time.time()

  def parse_opts(self, argv):
    argv = argv[:]
    for v in ['verbose', 'xml', 'timing']:
      if "--"+v in argv:
        setattr(self, v, True)
        argv.remove("--"+v)
    return argv

  def __call__(self, *things):
    if not self.verbose:
      return
    print(' '.join(str(x) for x in things))

  def lapse(self, *things):
    if not self.timing:
      return
    new_time = time.time()
    print("Took %0.3fs to %s" %(new_time - self.last_time,
                                 ' '.join(str(x) for x in things)))
    self.last_time = new_time

  def font(self, font, file=sys.stdout):
    if not self.xml:
      return
    from fontTools.misc import xmlWriter
    writer = xmlWriter.XMLWriter(file)
    font.disassembleInstructions = False  # Work around ttLib bug
    for tag in font.keys():
      writer.begintag(tag)
      writer.newline()
      font[tag].toXML(writer, font)
      writer.endtag(tag)
      writer.newline()


__all__ = [
  'Options',
  'Merger',
  'Logger',
  'main'
]

def main(args):

	log = Logger()
	args = log.parse_opts(args)

	options = Options()
	args = options.parse_opts(args)

	if len(args) < 1:
		print("usage: pyftmerge font...", file=sys.stderr)
		sys.exit(1)

	merger = Merger(options=options, log=log)
	font = merger.merge(args)
	outfile = 'merged.ttf'
	font.save(outfile)
	log.lapse("compile and save font")

	log.last_time = log.start_time
	log.lapse("make one with everything(TOTAL TIME)")

if __name__ == "__main__":
	main(sys.argv[1:])
