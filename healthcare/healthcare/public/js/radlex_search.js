frappe.ui.form.on('Procedure Type', {
    refresh(frm) {
        if (!frm.fields_dict.radlex_rpid) return;
        frm.add_custom_button('Search RadLex', () => {
            frappe.prompt([
                {fieldname: 'query', label: 'Search RadLex', fieldtype: 'Data', reqd: 1},
                {fieldname: 'modality', label: 'Modality (optional)', fieldtype: 'Select', options: '\nCT\nMR\nXR\nUS\nNM\nPET'},
                {fieldname: 'body_part', label: 'Body Part (optional)', fieldtype: 'Select', options: '\nChest\nAbdomen\nHead\nPelvis\nSpine\nExtremity'}
            ], values => {
                frappe.call({
                    method: 'healthcare.healthcare.radlex_search.search',
                    args: {query: values.query, modality: values.modality, body_part: values.body_part},
                    callback: r => {
                        if (r.message && r.message.length) {
                            const dialog = new frappe.ui.Dialog({
                                title: 'RadLex Results',
                                fields: [ { fieldtype: 'HTML', fieldname: 'results' } ]
                            });

                            const $wrapper = dialog.fields_dict.results.$wrapper;
                            const html = r.message.map((row, i) =>
                                `<div class="radlex-row" data-rpid="${row.rpid}" data-name="${row.name.replace(/"/g, '&quot;')}" data-desc="${row.description.replace(/"/g, '&quot;')}" style="padding:8px;border-bottom:1px solid #eee;cursor:pointer;">
                                    <strong>${row.rpid}</strong>: ${row.name}
                                    <div style="font-size:smaller;color:#666">${row.description}</div>
                                </div>`
                            ).join('');
                            $wrapper.html(html);

                            // clicking a row fills the form fields
                            $wrapper.find('.radlex-row').on('click', function() {
                                const $el = $(this);
                                const rpid = $el.attr('data-rpid');
                                const name = $el.attr('data-name');
                                const desc = $el.attr('data-desc');
                                frm.set_value('radlex_rpid', rpid);
                                frm.set_value('radlex_name', name);
                                frm.set_value('radlex_description', desc);
                                dialog.hide();
                            });

                            dialog.show();
                        } else {
                            frappe.msgprint('No results found.');
                        }
                    }
                });
            }, 'RadLex Search', 'Search');
        });
    }
});

frappe.ui.form.on('Procedure Step', {
    refresh(frm) {
        if (!frm.fields_dict.radlex_rpid) return;
        frm.add_custom_button('Search RadLex', () => {
            frappe.prompt([
                {fieldname: 'query', label: 'Search RadLex', fieldtype: 'Data', reqd: 1},
                {fieldname: 'modality', label: 'Modality (optional)', fieldtype: 'Select', options: '\nCT\nMR\nXR\nUS\nNM\nPET'},
                {fieldname: 'body_part', label: 'Body Part (optional)', fieldtype: 'Select', options: '\nChest\nAbdomen\nHead\nPelvis\nSpine\nExtremity'}
            ], values => {
                frappe.call({
                    method: 'healthcare.healthcare.radlex_search.search',
                    args: {query: values.query, modality: values.modality, body_part: values.body_part},
                    callback: r => {
                        if (r.message && r.message.length) {
                            const dialog = new frappe.ui.Dialog({
                                title: 'RadLex Results',
                                fields: [ { fieldtype: 'HTML', fieldname: 'results' } ]
                            });

                            const $wrapper = dialog.fields_dict.results.$wrapper;
                            const html = r.message.map((row, i) =>
                                `<div class="radlex-row" data-rpid="${row.rpid}" data-name="${row.name.replace(/"/g, '&quot;')}" data-desc="${row.description.replace(/"/g, '&quot;')}" style="padding:8px;border-bottom:1px solid #eee;cursor:pointer;">
                                    <strong>${row.rpid}</strong>: ${row.name}
                                    <div style="font-size:smaller;color:#666">${row.description}</div>
                                </div>`
                            ).join('');
                            $wrapper.html(html);

                            // clicking a row fills the form fields
                            $wrapper.find('.radlex-row').on('click', function() {
                                const $el = $(this);
                                const rpid = $el.attr('data-rpid');
                                const name = $el.attr('data-name');
                                const desc = $el.attr('data-desc');
                                frm.set_value('radlex_rpid', rpid);
                                frm.set_value('radlex_name', name);
                                frm.set_value('radlex_description', desc);
                                dialog.hide();
                            });

                            dialog.show();
                        } else {
                            frappe.msgprint('No results found.');
                        }
                    }
                });
            }, 'RadLex Search', 'Search');
        });
    }
});
